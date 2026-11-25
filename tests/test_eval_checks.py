"""Tests for the eval checks, with small fake answers and fake scores."""

import json

import pytest

from app import scoring, tools
from app.schemas import FinalAnswer, RankedHub
from evals import checks


def answer(text="", ranking=(), reasoning=(), confidence="high"):
    return FinalAnswer(answer=text, ranking=list(ranking), reasoning=list(reasoning),
                       assumptions=[], confidence=confidence, complete=True)


def entry(hub_id, category, score):
    return RankedHub(hub_id=hub_id, hub_name=hub_id, category=category, score=score, note="")


def tool_call(name, output, turn=1):
    return {"turn": turn, "name": name, "input": {}, "output": json.dumps(output),
            "is_error": False}


@pytest.fixture
def fake_scores(monkeypatch):
    def fake_score_hub(hub):
        score = {"miami": 98.9, "houston": 90.5}.get(hub["id"], 10.0)
        return {"overall": 50.0, "categories": {"hurricane": {"score": score}}}

    monkeypatch.setattr(scoring, "score_hub", fake_score_hub)
    monkeypatch.setattr(tools, "rank_hubs", lambda category=None, region=None: {
        "hubs": [{"hub_id": "miami"}, {"hub_id": "houston"}, {"hub_id": "atlanta"}]})


def test_numbers_in_text():
    assert checks.numbers_in("1,826 days, the 98.4th percentile, 2021-2025") == \
        [1826.0, 98.4, 2021.0, 2025.0]


def test_numbers_from_tools_pass_and_invented_ones_fail():
    log = [tool_call("compare_hubs", {"flood": 98.9, "note": "23.6 days"})]
    good = checks.Run(["q"], answer("Houston 98.9, rounded 99, rain 23.6, top 3"), log)
    assert checks.no_invented_numbers(good)[0]
    bad = checks.Run(["q"], answer("Houston leads by 13.0 points"), log)
    passed, detail = checks.no_invented_numbers(bad)
    assert not passed and "13.0" in detail


def test_numbers_from_question_and_prompt_are_allowed():
    run = checks.Run(["What about 2015?"], answer("No data for 2015; 70% NRI, 30% observed"))
    assert checks.no_invented_numbers(run)[0]


RATIO_OUTPUT = tool_call("compare_hubs", {"count_ratios": [{"ratios": [
    {"metric": "heavy_rain_days_per_year", "ratio": 2.6},
    {"metric": "hot_days_per_year", "ratio": 2.0}]}]})


@pytest.mark.parametrize("text", [
    "2.6 times as many heavy-rain days", "about twice as many hot days",
])
def test_ratios_returned_by_tools_pass(text):
    assert checks.ratios_from_tools(checks.Run(["q"], answer(text), [RATIO_OUTPUT]))[0]


@pytest.mark.parametrize("text", [
    "3.5 times more rain", "3x the snow", "triple the storms", "40% more days",
])
def test_ratios_not_returned_by_tools_fail(text):
    assert not checks.ratios_from_tools(checks.Run(["q"], answer(text), [RATIO_OUTPUT]))[0]


def test_plain_comparison_is_not_flagged():
    run = checks.Run(["q"], answer("Houston has far more heavy-rain days (23.6 vs 9.2). "
                                   "Hurricanes hit about 0.30 times a year."))
    assert checks.ratios_from_tools(run)[0]


def test_scores_match_tools(fake_scores):
    right = checks.Run(["q"], answer(ranking=[entry("miami", "hurricane", 98.9)]))
    wrong = checks.Run(["q"], answer(ranking=[entry("miami", "hurricane", 95.0)]))
    assert checks.scores_match_tools(right)[0]
    assert not checks.scores_match_tools(wrong)[0]


def test_unknown_hub_in_ranking_fails(fake_scores):
    run = checks.Run(["q"], answer(ranking=[entry("boise", "winter", 80.0)]))
    passed, detail = checks.scores_match_tools(run)
    assert not passed and "not one of our hubs" in detail


def test_ranking_matches_compares_order(fake_scores):
    right = checks.Run(["q"], answer(ranking=[entry("miami", "hurricane", 98.9),
                                              entry("houston", "hurricane", 90.5)]))
    wrong = checks.Run(["q"], answer(ranking=[entry("houston", "hurricane", 90.5)]))
    assert checks.ranking_matches(right, top=2, category="hurricane")[0]
    assert not checks.ranking_matches(wrong, top=2, category="hurricane")[0]


def test_tools_called_only_counts_the_last_turn():
    log = [tool_call("rank_hubs", {}, turn=1), tool_call("list_hubs", [], turn=2)]
    run = checks.Run(["q1", "q2"], answer(), log, last_turn=2)
    assert not checks.tools_called(run, ["rank_hubs"])[0]
    assert checks.tools_called(run, ["list_hubs"])[0]


def test_mentions_and_ranking_empty():
    run = checks.Run(["q"], answer("We don't have a hub in Boise."))
    assert checks.mentions(run, ["don't have"])[0]
    assert checks.ranking_empty(run)[0]


def test_run_checks_runs_defaults_and_case_checks():
    run = checks.Run(["q"], answer("No forecast available."))
    results = checks.run_checks(run, [{"check": "mentions", "any_of": ["forecast"]}])
    assert [name for name, _, _ in results] == \
        ["scores_match_tools", "no_invented_numbers", "ratios_from_tools", "mentions"]
    assert all(passed for _, passed, _ in results)


def test_cases_file_is_valid():
    import inspect
    from pathlib import Path

    cases = json.loads((Path(__file__).parent.parent / "evals" / "cases.json").read_text())
    assert len({c["id"] for c in cases}) == len(cases)       # unique ids
    for case in cases:
        assert case["questions"]
        for spec in case["checks"]:
            check = checks.CASE_CHECKS[spec["check"]]
            params = {k for k in spec if k != "check"}
            inspect.signature(check).bind(None, **dict.fromkeys(params))

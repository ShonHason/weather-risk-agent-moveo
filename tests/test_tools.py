"""Tests for the agent's tools. Scoring is replaced by fake, fixed scores."""

import json

import pytest

from app import metrics, scoring, tools
from app import scoring_config as config

# Fake overall/winter scores per hub id; every other value is 10.
FAKE_SCORES = {"chicago": 60, "minneapolis": 80, "detroit": 70, "miami": 90}


def fake_score_hub(hub, db_path=None):
    score = FAKE_SCORES.get(hub["id"], 10)
    return {
        "hub_id": hub["id"], "name": hub["name"], "region": hub["region"],
        "overall": score,
        "categories": {c: {"score": score if c == "winter" else 10}
                       for c in config.CATEGORY_HAZARDS},
        "nri_hazards": {h: {"frequency": 1.0, "frequency_percentile": 50.0}
                        for hs in config.CATEGORY_HAZARDS.values() for h in hs},
    }


@pytest.fixture(autouse=True)
def fake_scoring(monkeypatch):
    monkeypatch.setattr(scoring, "score_hub", fake_score_hub)
    monkeypatch.setattr(metrics, "get_hub_metrics",
                        lambda hub, year=None, db_path=None: {"year": year, "snow_days_pct": 10.1})


def test_list_hubs_filters_by_region():
    midwest = tools.list_hubs("Midwest")
    assert {h["region"] for h in midwest} == {"Midwest"}
    assert "chicago" in {h["id"] for h in midwest}


def test_find_hub_by_id_name_or_city():
    assert tools.find_hub("MIAMI")["id"] == "miami"
    assert tools.find_hub("Miami Hub")["id"] == "miami"
    assert tools.find_hub("salt_lake_city")["id"] == "salt_lake_city"
    with pytest.raises(ValueError):
        tools.find_hub("Atlantis")


def test_rank_hubs_by_category_in_a_region():
    result = tools.rank_hubs(category="winter", region="Midwest", top_n=3)
    assert [h["hub_id"] for h in result["hubs"]] == ["minneapolis", "detroit", "chicago"]
    assert result["hubs"][0]["rank"] == 1
    assert result["ranked_by"] == "winter"


def test_get_hub_metrics_adds_single_year_metrics():
    result = tools.get_hub_metrics("denver", year=2025)
    assert result["hub_id"] == "denver"
    assert result["metrics_for_year"]["year"] == 2025


def test_compare_hubs_shows_only_requested_categories_with_nri_detail():
    result = tools.compare_hubs(["Miami", "Houston"], ["hurricane", "flood"])
    assert [h["hub_id"] for h in result["hubs"]] == ["miami", "houston"]
    flood = result["hubs"][0]["categories"]["flood"]
    assert set(flood["nri_hazards"]) == {"inland_flooding", "coastal_flooding"}
    assert set(result["hubs"][0]["categories"]) == {"hurricane", "flood"}


def test_compare_hubs_returns_average_and_highest_hub():
    # Fake scores: winter = the hub's score (miami 90, chicago 60), others 10.
    result = tools.compare_hubs(["Miami", "Chicago"], ["winter", "heat"])
    miami, chicago = result["hubs"]
    assert miami["average_of_chosen_categories"] == 50.0      # (90 + 10) / 2
    assert chicago["average_of_chosen_categories"] == 35.0    # (60 + 10) / 2
    assert result["highest_hub"]["winter"] == "miami"
    assert result["highest_hub"]["average_of_chosen_categories"] == "miami"


def test_run_tool_returns_json():
    output, is_error = tools.run_tool("list_hubs", {"region": "West"})
    assert not is_error
    assert all(h["region"] == "West" for h in json.loads(output))


def test_run_tool_reports_bad_input_as_error():
    output, is_error = tools.run_tool("get_hub_metrics", {"hub": "Atlantis"})
    assert is_error and "Unknown hub" in output
    assert tools.run_tool("no_such_tool", {})[1] is True


def test_every_tool_has_a_definition():
    assert {t["name"] for t in tools.TOOL_DEFINITIONS} == set(tools.TOOLS)

"""Deterministic checks for the eval set.

Each check gets a Run (the agent's final answer, its tool calls and the
questions) and returns (passed, detail). Expected values are computed by our
own code at eval time, so the checks stay correct if the data is refreshed.
"""

import json
import re
from dataclasses import dataclass, field

from app import metrics, scoring, tools
from app.agent import SYSTEM_PROMPT
from app.schemas import FinalAnswer

TOLERANCE = 0.051   # numbers are shown with 1 decimal


@dataclass
class Run:
    questions: list              # every question asked in the conversation
    answer: FinalAnswer          # the final answer (to the last question)
    tool_log: list = field(default_factory=list)   # Agent.tool_log
    last_turn: int = 1


# --- helpers ---------------------------------------------------------------

NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def numbers_in(text):
    """All numbers written in a text: "1,826 days, 98.4th" -> [1826.0, 98.4]."""
    return [float(n.replace(",", "")) for n in NUMBER.findall(text)]


def numbers_in_json(value):
    """All numbers inside a tool output (JSON text), including inside strings."""
    found = []

    def walk(item):
        if isinstance(item, bool):
            return
        if isinstance(item, (int, float)):
            found.append(float(item))
        elif isinstance(item, str):
            found.extend(numbers_in(item))
        elif isinstance(item, dict):
            for v in item.values():
                walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)

    try:
        walk(json.loads(value))
    except ValueError:
        found.extend(numbers_in(value))
    return found


def answer_text(answer):
    """Everything the user reads, as one text."""
    parts = [answer.answer, *answer.reasoning, *answer.assumptions]
    parts += [hub.note for hub in answer.ranking]
    return "\n".join(parts)


def close(x, y):
    """Same number, allowing for rounding to 0 or 1 decimals."""
    return abs(x - y) <= TOLERANCE or (x == int(x) and round(y) == x)


def category_score(hub_id, category):
    scored = scoring.score_hub(tools.find_hub(hub_id))
    if category == "overall":
        return scored["overall"]
    return scored["categories"][category]["score"]


# --- checks run on every case ---------------------------------------------

def scores_match_tools(run):
    """Every ranking entry is a real hub, and its score equals our code's score."""
    wrong = []
    for hub in run.answer.ranking:
        try:
            expected = category_score(hub.hub_id, hub.category)
        except ValueError:
            wrong.append(f"{hub.hub_id}: not one of our hubs")
            continue
        if not close(hub.score, expected):
            wrong.append(f"{hub.hub_id}/{hub.category}: {hub.score} (expected {expected})")
    return not wrong, "; ".join(wrong) or "all ranking scores match"


def no_invented_numbers(run):
    """Every number in the answer comes from a tool, the prompt or the question.

    Small whole numbers (0-10, e.g. "top 3", "two hubs") are always allowed.
    """
    allowed = numbers_in(SYSTEM_PROMPT)
    for question in run.questions:
        allowed += numbers_in(question)
    for call in run.tool_log:
        allowed += numbers_in_json(call["output"])

    invented = []
    for number in numbers_in(answer_text(run.answer)):
        is_small_count = number == int(number) and 0 <= number <= 10
        if not is_small_count and not any(close(number, a) for a in allowed):
            invented.append(number)
    invented = sorted(set(invented))
    return not invented, f"not from tools: {invented}" if invented else "all numbers from tools"


RATIO = re.compile(
    r"\b(twice|thrice|double|triple|half as|"
    r"(two|three|four|five|ten|\d+(\.\d+)?) ?(times(?! (a|per) year)|x|×))\b"
    r"|\d+(\.\d+)? ?% (more|higher|lower|less|fewer)\b",
    re.IGNORECASE,
)
RATIO_WORDS = {"twice": 2, "double": 2, "two": 2, "thrice": 3, "triple": 3,
               "three": 3, "four": 4, "five": 5, "ten": 10, "half as": 2}


def tool_ratios(run):
    """Every "ratio" value the tools returned (from compare_hubs count_ratios)."""
    found = []

    def walk(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if key == "ratio" and isinstance(value, (int, float)):
                    found.append(float(value))
                else:
                    walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    for call in run.tool_log:
        try:
            walk(json.loads(call["output"]))
        except ValueError:
            pass
    return found


def ratios_from_tools(run):
    """Any ratio wording ("2.6 times", "twice") matches a ratio a tool returned.
    Percent changes ("40% more") are never returned by tools, so always fail."""
    allowed = tool_ratios(run)
    bad = []
    for match in RATIO.finditer(answer_text(run.answer)):
        phrase = match.group(0)
        number = numbers_in(phrase)
        word = next((w for w in RATIO_WORDS if phrase.lower().startswith(w)), None)
        if "%" in phrase:
            value = None
        elif number:
            value = number[0]
        else:
            value = RATIO_WORDS.get(word)
        # Exact match (to 1 decimal): "3x" for a ratio of 2.6 is the model
        # rounding, i.e. its own number.
        if value is None or not any(abs(value - a) <= TOLERANCE for a in allowed):
            bad.append(phrase)
    return not bad, f"ratio not from tools: {bad}" if bad else "all ratios from tools"


DEFAULT_CHECKS = [scores_match_tools, no_invented_numbers, ratios_from_tools]


# --- case-specific checks (named in evals/cases.json) ---------------------

def tools_called(run, any_of):
    """At least one of these tools was called for the last question."""
    called = sorted({c["name"] for c in run.tool_log if c["turn"] == run.last_turn})
    return bool(set(any_of) & set(called)), f"called {called}"


def ranking_matches(run, top, category=None, region=None):
    """The ranking starts with the same hubs, in the same order, as our code."""
    expected = [h["hub_id"] for h in tools.rank_hubs(category, region)["hubs"][:top]]
    actual = [h.hub_id for h in run.answer.ranking][:top]
    return actual == expected, f"got {actual}, expected {expected}"


def ranking_includes(run, hubs, category):
    """The ranking has an entry for each of these hubs in this category."""
    present = {(h.hub_id, h.category) for h in run.answer.ranking}
    missing = [hub for hub in hubs if (hub, category) not in present]
    return not missing, f"missing {category} entries for {missing}" if missing else "all present"


def ranking_empty(run):
    count = len(run.answer.ranking)
    return count == 0, f"{count} ranking entries"


def number_in_answer(run, hub, metric, year=None):
    """The answer states this metric's value (as computed by our code)."""
    expected = metrics.get_hub_metrics(tools.find_hub(hub), year)[metric]
    found = numbers_in(run.answer.answer)
    ok = any(close(n, expected) for n in found)
    return ok, f"expected {expected}, answer has {found}"


def mentions(run, any_of):
    """The answer text mentions at least one of these phrases (any case)."""
    text = answer_text(run.answer).lower()
    hits = [p for p in any_of if p.lower() in text]
    return bool(hits), f"found {hits}" if hits else f"none of {any_of}"


def confidence_in(run, values):
    return run.answer.confidence in values, f"confidence {run.answer.confidence}"


CASE_CHECKS = {
    "tools_called": tools_called,
    "ranking_matches": ranking_matches,
    "ranking_includes": ranking_includes,
    "ranking_empty": ranking_empty,
    "number_in_answer": number_in_answer,
    "mentions": mentions,
    "confidence_in": confidence_in,
}


def run_checks(run, case_checks):
    """Run the default checks plus the case's own. Returns [(name, passed, detail)]."""
    results = []
    for check in DEFAULT_CHECKS:
        results.append((check.__name__, *check(run)))
    for spec in case_checks:
        params = {k: v for k, v in spec.items() if k != "check"}
        passed, detail = CASE_CHECKS[spec["check"]](run, **params)
        results.append((spec["check"], passed, detail))
    return results

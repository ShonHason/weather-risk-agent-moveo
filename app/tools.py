"""The tools Claude can call. Each one is plain, deterministic Python.

Claude decides WHICH tool to call; the numbers always come from our code
(app/scoring.py and app/metrics.py), never from the model.

TOOL_DEFINITIONS is what we send to Claude. run_tool() executes a call.
"""

import json

from app import metrics, scoring
from app import scoring_config as config
from app.hubs import STATE_TO_REGION, load_hubs

CATEGORIES = list(config.CATEGORY_HAZARDS)
REGIONS = sorted(set(STATE_TO_REGION.values()))


# --- the tools ------------------------------------------------------------

def list_hubs(region=None):
    """All hubs (optionally in one region), with their location."""
    hubs = [h for h in load_hubs() if region is None or h["region"] == region]
    return [{key: hub[key] for key in ("id", "name", "city", "state", "region")}
            for hub in hubs]


def get_hub_metrics(hub, year=None):
    """Full risk breakdown and weather metrics for one hub.

    The score always uses the 5-year period. If year is given, the weather
    metrics for that single year are added as well.
    """
    result = scoring.score_hub(find_hub(hub))
    if year is not None:
        result["metrics_for_year"] = metrics.get_hub_metrics(find_hub(hub), year)
    return result


def rank_hubs(category=None, region=None, top_n=None):
    """Hubs ranked by overall score, or by one category, highest risk first."""
    hubs = [h for h in load_hubs() if region is None or h["region"] == region]
    ranked = scoring.rank([scoring.score_hub(h) for h in hubs], category)
    if top_n is not None:
        ranked = ranked[:top_n]
    return {
        "ranked_by": category or "overall",
        "region": region or "all",
        "hubs": [_summary(h, rank) for rank, h in enumerate(ranked, start=1)],
    }


def compare_hubs(hubs, categories=None):
    """Side-by-side breakdown for two or more hubs, for chosen categories."""
    categories = categories or CATEGORIES
    comparison = []
    for name in hubs:
        scored = scoring.score_hub(find_hub(name))
        comparison.append({
            "hub_id": scored["hub_id"],
            "name": scored["name"],
            "region": scored["region"],
            "overall": scored["overall"],
            "categories": {c: _category_detail(scored, c) for c in categories},
        })
    return {"hubs": comparison}


# --- helpers ---------------------------------------------------------------

def find_hub(text):
    """Find a hub by id, name or city, ignoring case ("Miami" -> miami hub)."""
    wanted = text.strip().lower()
    for hub in load_hubs():
        if wanted in (hub["id"], hub["name"].lower(), hub["city"].lower()):
            return hub
    known = ", ".join(h["city"] for h in load_hubs())
    raise ValueError(f"Unknown hub '{text}'. Known hubs: {known}")


def _summary(scored, rank):
    return {
        "rank": rank,
        "hub_id": scored["hub_id"],
        "name": scored["name"],
        "region": scored["region"],
        "overall": scored["overall"],
        "category_scores": {c: r["score"] for c, r in scored["categories"].items()},
    }


def _category_detail(scored, category):
    """A category's score plus the raw NRI hazards and observed value behind it."""
    hazards = config.CATEGORY_HAZARDS[category]
    return {
        **scored["categories"][category],
        "nri_hazards": {h: scored["nri_hazards"][h] for h in hazards},
    }


# --- what Claude sees ------------------------------------------------------

_HUB = {"type": "string", "description": "Hub id, name or city, e.g. 'denver' or 'Miami'."}
_CATEGORY = {"type": "string", "enum": CATEGORIES}
_REGION = {"type": "string", "enum": REGIONS,
           "description": "US Census region. Omit for all hubs."}

TOOL_DEFINITIONS = [
    {
        "name": "list_hubs",
        "description": "List the company's hubs with city, state and region.",
        "input_schema": {
            "type": "object",
            "properties": {"region": _REGION},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_hub_metrics",
        "description": (
            "Full risk breakdown for ONE hub: overall score, each category's score "
            "with its NRI and observed parts, raw NRI hazard frequencies, and "
            "5-year weather metrics. Give 'year' to also get that single year's "
            "weather metrics (e.g. percentage of days with snowfall)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hub": _HUB,
                "year": {"type": "integer", "description": "A calendar year inside the data period."},
            },
            "required": ["hub"],
            "additionalProperties": False,
        },
    },
    {
        "name": "rank_hubs",
        "description": (
            "Rank hubs by overall risk score, or by one hazard category, highest "
            "risk first. Optionally only one region, and only the top N."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {**_CATEGORY, "description": "Rank by this category. Omit for overall."},
                "region": _REGION,
                "top_n": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_hubs",
        "description": (
            "Compare two or more hubs side by side: category scores with the NRI "
            "hazard frequencies and observed weather behind them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hubs": {"type": "array", "items": _HUB},
                "categories": {
                    "type": "array", "items": _CATEGORY,
                    "description": "Categories to compare. Omit for all five.",
                },
            },
            "required": ["hubs"],
            "additionalProperties": False,
        },
    },
]

TOOLS = {
    "list_hubs": list_hubs,
    "get_hub_metrics": get_hub_metrics,
    "rank_hubs": rank_hubs,
    "compare_hubs": compare_hubs,
}


def run_tool(name, tool_input):
    """Run one tool call. Returns (result as JSON text, is_error)."""
    if name not in TOOLS:
        return f"Unknown tool '{name}'", True
    try:
        return json.dumps(TOOLS[name](**tool_input)), False
    except (ValueError, TypeError, KeyError) as error:
        # Bad input (e.g. unknown hub): tell Claude so it can correct itself.
        return f"Error: {error}", True

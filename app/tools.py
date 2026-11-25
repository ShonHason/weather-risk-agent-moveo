"""The tools Claude can call. Each one is plain, deterministic Python.

Claude decides WHICH tool to call; the numbers always come from our code
(app/scoring.py, app/metrics.py and app/forecast.py), never from the model.

TOOL_DEFINITIONS is what we send to Claude. run_tool() executes a call.
"""

import json

from app import forecast, metrics, scoring
from app import scoring_config as config
from app.hubs import STATE_TO_REGION, load_hubs

CATEGORIES = list(config.CATEGORY_HAZARDS)
REGIONS = sorted(set(STATE_TO_REGION.values()))

# Yearly weather counts that belong to each category (for count ratios).
CATEGORY_WEATHER_COUNTS = {
    "winter": ["snow_days_per_year", "freezing_days_per_year"],
    "heat": ["hot_days_per_year"],
    "flood": ["heavy_rain_days_per_year"],
    "severe_storm": ["windy_days_per_year"],
    "hurricane": [],
}


# --- the tools ------------------------------------------------------------

def list_hubs(region=None):
    """All hubs (optionally in one region), with their location and the count.

    The count is included so Claude never has to count hubs itself.
    """
    hubs = [h for h in load_hubs() if region is None or h["region"] == region]
    return {
        "count": len(hubs),
        "hubs": [{key: hub[key] for key in ("id", "name", "city", "state", "region")}
                 for hub in hubs],
    }


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
    """Hubs ranked by overall score, or by one category, highest risk first.

    Also returns numbers Claude would otherwise calculate itself:
    - gap_to_next: how far each hub's score is above the next hub's
      (None for the last hub), in the score the ranking is by;
    - score_ranges: the lowest and highest score among the returned hubs, for
      the overall score and each category ("between 85.8 and 98.9").
    """
    hubs = [h for h in load_hubs() if region is None or h["region"] == region]
    ranked = scoring.rank([scoring.score_hub(h) for h in hubs], category)
    if top_n is not None:
        ranked = ranked[:top_n]
    summaries = [_summary(h, rank) for rank, h in enumerate(ranked, start=1)]

    def ranked_score(hub):
        return hub["overall"] if category is None else hub["category_scores"][category]

    for this_hub, next_hub in zip(summaries, summaries[1:] + [None]):
        this_hub["gap_to_next"] = (
            None if next_hub is None
            else round(ranked_score(this_hub) - ranked_score(next_hub), 1)
        )

    return {
        "ranked_by": category or "overall",
        "region": region or "all",
        "hubs": summaries,
        "score_ranges": _score_ranges(summaries),
    }


def compare_hubs(hubs, categories=None):
    """Side-by-side breakdown for two or more hubs, for chosen categories.

    Also returns the numbers an analyst usually wants from a comparison, so
    Claude never has to calculate them: each hub's average over the chosen
    categories, which hub scores highest in each category, the gap between
    every pair of compared hubs (which one is higher, and by how much), and
    ratios of yearly counts between every pair ("2.6 times as many heavy-rain
    days"). Ratios are only for counts, never for the 0-100 scores: a ratio
    of two percentiles has no meaning.
    """
    categories = categories or CATEGORIES
    comparison = []
    all_scored = []
    for name in hubs:
        scored = scoring.score_hub(find_hub(name))
        all_scored.append(scored)
        scores = [scored["categories"][c]["score"] for c in categories]
        comparison.append({
            "hub_id": scored["hub_id"],
            "name": scored["name"],
            "region": scored["region"],
            "overall": scored["overall"],
            "average_of_chosen_categories": round(sum(scores) / len(scores), 1),
            "categories": {c: _category_detail(scored, c) for c in categories},
        })

    highest = {
        c: max(comparison, key=lambda hub: hub["categories"][c]["score"])["hub_id"]
        for c in categories
    }
    highest["average_of_chosen_categories"] = max(
        comparison, key=lambda hub: hub["average_of_chosen_categories"])["hub_id"]

    return {"categories": categories, "hubs": comparison, "highest_hub": highest,
            "gaps": _pair_gaps(comparison, categories),
            "count_ratios": _pair_count_ratios(all_scored, categories)}


# --- helpers ---------------------------------------------------------------

def get_forecast_risk(hub):
    """Short-term risk for one hub from the 7-day forecast (not the long-term score)."""
    result = forecast.score_hub_forecast(find_hub(hub))
    result["scales"] = config.FORECAST_SCALES   # so Claude can explain the score
    return result


def find_hub(text):
    """Find a hub by id, name or city, ignoring case ("Miami" -> miami hub)."""
    wanted = text.strip().lower()
    for hub in load_hubs():
        if wanted in (hub["id"], hub["name"].lower(), hub["city"].lower()):
            return hub
    known = [h["city"] for h in load_hubs()]
    raise ValueError(f"Unknown hub '{text}'. The {len(known)} known hubs are: "
                     f"{', '.join(known)}")


def _summary(scored, rank):
    return {
        "rank": rank,
        "hub_id": scored["hub_id"],
        "name": scored["name"],
        "region": scored["region"],
        "overall": scored["overall"],
        "category_scores": {c: r["score"] for c, r in scored["categories"].items()},
    }


def _pair_gaps(comparison, categories):
    """For every pair of compared hubs and every score: which hub is higher
    and by how much (always positive, so Claude never flips a sign).

    Example: {"hubs": ["houston", "miami"],
              "flood": {"higher": "houston", "gap": 13.0}, ...}
    """
    def gap(a_hub, a_score, b_hub, b_score):
        if a_score == b_score:
            return {"higher": None, "gap": 0.0}
        higher = a_hub if a_score > b_score else b_hub
        return {"higher": higher, "gap": round(abs(a_score - b_score), 1)}

    gaps = []
    for i, a in enumerate(comparison):
        for b in comparison[i + 1:]:
            pair = {"hubs": [a["hub_id"], b["hub_id"]]}
            for name in ["overall", "average_of_chosen_categories"]:
                pair[name] = gap(a["hub_id"], a[name], b["hub_id"], b[name])
            for c in categories:
                pair[c] = gap(a["hub_id"], a["categories"][c]["score"],
                              b["hub_id"], b["categories"][c]["score"])
            gaps.append(pair)
    return gaps


def _pair_count_ratios(all_scored, categories):
    """For every pair of hubs: how many times higher one hub's yearly counts are.

    Covers the observed weather days of the chosen categories and the NRI
    hazard events per year. Example entry:
        {"metric": "heavy_rain_days_per_year", "higher": "houston",
         "higher_value": 23.6, "lower_value": 9.2, "ratio": 2.6}
    ratio is None when the lower value is 0 (it would be infinite).
    """
    def counts(scored):
        values = {}
        for c in categories:
            for metric in CATEGORY_WEATHER_COUNTS[c]:
                values[metric] = scored["metrics"][metric]
            for hazard in config.CATEGORY_HAZARDS[c]:
                values[f"{hazard}_events_per_year"] = scored["nri_hazards"][hazard]["frequency"] or 0.0
        return values

    pairs = []
    for i, a in enumerate(all_scored):
        for b in all_scored[i + 1:]:
            a_counts, b_counts = counts(a), counts(b)
            ratios = []
            for metric in a_counts:
                a_value, b_value = a_counts[metric], b_counts[metric]
                if a_value == b_value:
                    continue   # equal counts: no ratio worth stating
                higher, high, low = ((a["hub_id"], a_value, b_value) if a_value > b_value
                                     else (b["hub_id"], b_value, a_value))
                ratios.append({"metric": metric, "higher": higher,
                               "higher_value": high, "lower_value": low,
                               "ratio": round(high / low, 1) if low > 0 else None})
            pairs.append({"hubs": [a["hub_id"], b["hub_id"]], "ratios": ratios})
    return pairs


def _score_ranges(summaries):
    """{"overall": {"min": .., "max": ..}, "winter": {...}, ...} over these hubs."""
    columns = {"overall": [h["overall"] for h in summaries]}
    for c in CATEGORIES:
        columns[c] = [h["category_scores"][c] for h in summaries]
    return {name: {"min": min(values), "max": max(values)}
            for name, values in columns.items() if values}


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
            "risk first. Optionally only one region, and only the top N. Also "
            "returns each hub's gap to the next hub, and the min and max score "
            "of the returned hubs per category."
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
            "hazard frequencies and observed weather behind them, each hub's "
            "average over the chosen categories, the highest hub per category, "
            "the score gaps between every pair of compared hubs, and ratios of "
            "yearly counts (weather days, hazard events) between every pair."
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
    {
        "name": "get_forecast_risk",
        "description": (
            "Short-term risk for ONE hub over the next 7 days, from the weather "
            "forecast: a 0-100 score (its worst hazard), each hazard's worst day "
            "and score (snow, heavy_rain, wind, heat, cold), the daily forecast "
            "values and the scales used. Separate from the long-term risk score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"hub": _HUB},
            "required": ["hub"],
            "additionalProperties": False,
        },
    },
]

TOOLS = {
    "list_hubs": list_hubs,
    "get_hub_metrics": get_hub_metrics,
    "rank_hubs": rank_hubs,
    "compare_hubs": compare_hubs,
    "get_forecast_risk": get_forecast_risk,
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
    except OSError as error:
        # A live API (the forecast) is unreachable: Claude can say so.
        return f"Error: data source unavailable: {error}", True

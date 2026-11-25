"""Short-term risk score from the 7-day weather forecast.

Separate from the long-term score (scoring.py): that one ranks long-term
exposure for investment decisions; this one says what the coming week looks
like, and feeds the risk-change alert (alerts.py).

Each hazard on each forecast day gets two scores, and the higher counts:
- absolute: the value on a fixed scale (15 cm of snow = 100 anywhere);
- relative: how unusual the value is for THIS hub in this calendar month,
  compared with its own 2021-2025 history (-8 °C is extreme in Dallas,
  normal in Minneapolis). Counts only on a disruptive day.
An unusual day that is not disruptive (e.g. 14 mm of rain where November
is usually dry) becomes an info note: it never raises the score.

Sources: Open-Meteo Forecast API (never cached, a forecast changes every
few hours) and the Open-Meteo history we already cache for the long-term
score. Both free, no API key.

    python -m app.forecast          # prints every hub's score (real API)
"""

import calendar

from app import scoring_config as config
from app import weather
from app.fetch import fetch_json
from app.hubs import load_hubs
from app.weather import DAILY_VARIABLES

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_forecast(lat, lon):
    """Return the daily forecast for the next FORECAST_DAYS days.

    Same shape as weather.fetch_daily_weather:
        {"date": ["2026-11-25", ...], "snowfall_cm": [0.0, ...], ...}
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(DAILY_VARIABLES),
        "forecast_days": config.FORECAST_DAYS,
        "timezone": "auto",
    }
    daily = fetch_json(FORECAST_URL, params, use_cache=False)["daily"]

    result = {"date": daily["time"]}
    for api_name, our_name in DAILY_VARIABLES.items():
        result[our_name] = daily[api_name]
    return result


def fetch_history(lat, lon):
    """The hub's daily weather of the last 5 full years (from the cache)."""
    start, end = weather.default_period()
    return weather.fetch_daily_weather(lat, lon, start, end)


def values_by_month(history):
    """Group past daily values by calendar month.

    {"12": {"temp_min_c": [all December values], ...}, "01": {...}, ...}
    """
    months = {}
    for i, day in enumerate(history["date"]):
        month = months.setdefault(day[5:7], {})
        for variable, values in history.items():
            if variable != "date" and values[i] is not None:
                month.setdefault(variable, []).append(values[i])
    return months


def scale(value, zero_at, full_at):
    """Map a value to 0-100: zero_at -> 0, full_at -> 100, linear, capped.

    Works in both directions, e.g. cold: zero_at -10 °C, full_at -30 °C.
    """
    fraction = (value - zero_at) / (full_at - zero_at)
    return round(100 * min(max(fraction, 0.0), 1.0), 1)


def percentile_in_history(value, past_values, lower_is_worse):
    """Share of past days that were less severe than value, in percent.

    100 = more severe than every past day. None without past data.
    """
    if not past_values:
        return None
    if lower_is_worse:   # cold: lower temperatures are worse
        less_severe = sum(1 for past in past_values if past > value)
    else:
        less_severe = sum(1 for past in past_values if past < value)
    return round(100 * less_severe / len(past_values), 1)


def is_disruptive(value, rule):
    """Same daily definitions as the long-term metrics (e.g. rain >= 25 mm,
    a freezing night = min below 0 °C)."""
    if rule["full_at"] < rule["zero_at"]:   # cold: lower is worse
        return value < rule["disruptive_from"]
    return value >= rule["disruptive_from"]


def day_score(value, rule, past_values):
    """Absolute, relative and combined score of one hazard on one day."""
    lower_is_worse = rule["full_at"] < rule["zero_at"]
    absolute = scale(value, rule["zero_at"], rule["full_at"])
    percentile = percentile_in_history(value, past_values, lower_is_worse)
    disruptive = is_disruptive(value, rule)

    relative = 0.0
    if percentile is not None and disruptive:
        relative = scale(percentile, config.RELATIVE_FROM_PERCENTILE, 100)

    return {"score": max(absolute, relative), "absolute": absolute,
            "relative": relative, "percentile": percentile,
            "disruptive": disruptive}


def is_unusual(scored):
    return (scored["percentile"] is not None
            and scored["percentile"] >= config.RELATIVE_FROM_PERCENTILE)


# What each hazard measures, for readable notes.
MEASURES = {"snow": "snowfall", "heavy_rain": "rain", "wind": "wind gusts",
            "heat": "max temperature", "cold": "min temperature"}


def unusual_note(hazard, rule, day, value, scored):
    """An info note for an unusual day that is not disruptive."""
    month = calendar.month_name[int(day[5:7])]
    higher_or_lower = "lower" if rule["full_at"] < rule["zero_at"] else "higher"
    return {
        "hazard": hazard, "date": day, "value": value, "unit": rule["unit"],
        "percentile": scored["percentile"],
        "note": (f"Unusual but not disruptive: {MEASURES[hazard]} {value} "
                 f"{rule['unit']} on {day} is {higher_or_lower} than "
                 f"{scored['percentile']}% of {month} days in the hub's history, "
                 f"short of the disruption threshold ({rule['disruptive_from']} "
                 f"{rule['unit']})."),
    }


def forecast_score(daily, history=None):
    """Score a forecast: each hazard's worst day, then the worst hazard.

    history: the hub's past daily weather, for the relative score. Without
    it, only the absolute score is used.
    Also returns "notes": per hazard, the most unusual day that is not
    disruptive (info only, not part of the score).

    Returns:
        {"score": 64.0, "hazard": "cold", "date": "2026-12-03", "value": -8.2,
         "unit": "°C", "absolute": 0.0, "relative": 64.0, "percentile": 96.4,
         "hazards": {"snow": {...}, "cold": {...}, ...}}
    "percentile": the share of the hub's past days in the same calendar
    month that were less severe.
    """
    past = values_by_month(history) if history else {}
    hazards = {}
    notes = []
    for hazard, rule in config.FORECAST_SCALES.items():
        worst = None
        note = None
        for day, value in zip(daily["date"], daily[rule["variable"]]):
            if value is None:   # missing forecast value
                continue
            past_values = past.get(day[5:7], {}).get(rule["variable"], [])
            scored = day_score(value, rule, past_values)
            if worst is None or scored["score"] > worst["score"]:
                worst = {**scored, "date": day, "value": value, "unit": rule["unit"]}
            if is_unusual(scored) and not scored["disruptive"]:
                if note is None or scored["percentile"] > note["percentile"]:
                    note = unusual_note(hazard, rule, day, value, scored)
        hazards[hazard] = worst or {"score": 0.0, "absolute": 0.0, "relative": 0.0,
                                    "percentile": None, "disruptive": False,
                                    "date": None, "value": None, "unit": rule["unit"]}
        if note:
            notes.append(note)

    worst_hazard = max(hazards, key=lambda name: hazards[name]["score"])
    return {"hazard": worst_hazard, **hazards[worst_hazard], "hazards": hazards,
            "notes": notes}


def score_hub_forecast(hub):
    """The short-term score for one hub, with its id and name."""
    daily = fetch_forecast(hub["lat"], hub["lon"])
    history = fetch_history(hub["lat"], hub["lon"])
    start, end = weather.default_period()
    return {"hub_id": hub["id"], "hub_name": hub["name"],
            "period": {"start": daily["date"][0], "end": daily["date"][-1]},
            "history_period": {"start": start.isoformat(), "end": end.isoformat()},
            **forecast_score(daily, history), "daily": daily}


if __name__ == "__main__":
    results = [score_hub_forecast(hub) for hub in load_hubs()]
    for r in sorted(results, key=lambda r: r["score"], reverse=True):
        print(f"{r['hub_name']:<20} {r['score']:5.1f}  {r['hazard']} {r['value']} "
              f"{r['unit']} on {r['date']}  (absolute {r['absolute']}, "
              f"relative {r['relative']}, worse than {r['percentile']}% of past days)")
        for note in r["notes"]:
            print(f"{'':<27}note: {note['note']}")

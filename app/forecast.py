"""Short-term risk score from the 7-day weather forecast.

Separate from the long-term score (scoring.py): that one ranks long-term
exposure for investment decisions; this one says what the coming week looks
like, and feeds the risk-change alert (alerts.py).

Source: Open-Meteo Forecast API. Free, no API key. Never cached, because a
forecast changes every few hours.

    python -m app.forecast          # prints every hub's score (real API)
"""

from app import scoring_config as config
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


def scale(value, zero_at, full_at):
    """Map a value to 0-100: zero_at -> 0, full_at -> 100, linear, capped.

    Works in both directions, e.g. cold: zero_at -10 °C, full_at -30 °C.
    """
    fraction = (value - zero_at) / (full_at - zero_at)
    return round(100 * min(max(fraction, 0.0), 1.0), 1)


def forecast_score(daily):
    """Score a forecast: each hazard's worst day, then the worst hazard.

    Returns:
        {"score": 64.0, "hazard": "snow", "date": "2026-11-27", "value": 9.6,
         "unit": "cm", "hazards": {"snow": {...}, "cold": {...}, ...}}
    """
    hazards = {}
    for hazard, rule in config.FORECAST_SCALES.items():
        worst = {"score": 0.0, "date": None, "value": None, "unit": rule["unit"]}
        for day, value in zip(daily["date"], daily[rule["variable"]]):
            if value is None:   # missing forecast value
                continue
            day_score = scale(value, rule["zero_at"], rule["full_at"])
            if worst["date"] is None or day_score > worst["score"]:
                worst = {"score": day_score, "date": day, "value": value,
                         "unit": rule["unit"]}
        hazards[hazard] = worst

    worst_hazard = max(hazards, key=lambda name: hazards[name]["score"])
    return {"hazard": worst_hazard, **hazards[worst_hazard], "hazards": hazards}


def score_hub_forecast(hub):
    """The short-term score for one hub, with its id and name."""
    daily = fetch_forecast(hub["lat"], hub["lon"])
    return {"hub_id": hub["id"], "hub_name": hub["name"],
            "period": {"start": daily["date"][0], "end": daily["date"][-1]},
            **forecast_score(daily), "daily": daily}


if __name__ == "__main__":
    results = [score_hub_forecast(hub) for hub in load_hubs()]
    for r in sorted(results, key=lambda r: r["score"], reverse=True):
        print(f"{r['hub_name']:<22} {r['score']:5.1f}  "
              f"{r['hazard']} {r['value']} {r['unit']} on {r['date']}")

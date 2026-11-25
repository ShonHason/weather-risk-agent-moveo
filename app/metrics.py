"""Turn daily weather history into simple, explainable metrics.

Example: "What percentage of days in Denver last year had snowfall?"
    get_hub_metrics(denver_hub, year=2025)["snow_days_pct"]
"""

from app import cache
from app import scoring_config as config
from app import weather


def compute_metrics(daily, year=None):
    """Count weather events in daily data (the output of fetch_daily_weather).

    If year is given, only that calendar year is used.
    Days with a missing value are skipped for that metric.
    """
    rows = _rows(daily, year)
    if not rows:
        raise ValueError(f"No weather data for year {year}")

    years = len({row["date"][:4] for row in rows})

    def count(variable, condition):
        return sum(1 for row in rows
                   if row[variable] is not None and condition(row[variable]))

    snow_days = count("snowfall_cm", lambda v: v >= config.SNOW_DAY_MIN_CM)
    heavy_rain_days = count("precipitation_mm",
                            lambda v: v >= config.HEAVY_RAIN_MIN_MM)
    hot_days = count("temp_max_c", lambda v: v >= config.HOT_DAY_MIN_C)
    freezing_days = count("temp_min_c", lambda v: v < config.FREEZING_DAY_MAX_C)
    windy_days = count("wind_gust_max_kmh",
                       lambda v: v >= config.WINDY_DAY_MIN_KMH)

    return {
        "period": f"{rows[0]['date']} to {rows[-1]['date']}",
        "days": len(rows),
        "years": years,
        "snow_days": snow_days,
        "snow_days_pct": round(100 * snow_days / len(rows), 1),
        "snow_days_per_year": round(snow_days / years, 1),
        "total_snowfall_cm": round(_total(rows, "snowfall_cm"), 1),
        "heavy_rain_days": heavy_rain_days,
        "heavy_rain_days_per_year": round(heavy_rain_days / years, 1),
        "hot_days": hot_days,
        "hot_days_per_year": round(hot_days / years, 1),
        "freezing_days": freezing_days,
        "freezing_days_per_year": round(freezing_days / years, 1),
        "windy_days": windy_days,
        "windy_days_per_year": round(windy_days / years, 1),
        "max_wind_gust_kmh": _max(rows, "wind_gust_max_kmh"),
    }


def get_hub_metrics(hub, year=None, db_path=cache.DB_PATH):
    """Weather metrics for one hub: the full 5-year period, or one year of it."""
    start, end = weather.default_period()
    if year is not None and not start.year <= year <= end.year:
        raise ValueError(
            f"Year {year} is outside the data period {start.year}-{end.year}"
        )
    daily = weather.fetch_daily_weather(hub["lat"], hub["lon"], start, end, db_path)
    return compute_metrics(daily, year)


def _rows(daily, year):
    """Turn the column lists into one dict per day, optionally for one year."""
    names = list(daily)
    rows = [dict(zip(names, values)) for values in zip(*daily.values())]
    if year is not None:
        rows = [row for row in rows if row["date"].startswith(str(year))]
    return rows


def _total(rows, variable):
    return sum(row[variable] for row in rows if row[variable] is not None)


def _max(rows, variable):
    values = [row[variable] for row in rows if row[variable] is not None]
    return max(values) if values else None

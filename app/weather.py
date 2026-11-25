"""Open-Meteo client: observed daily weather history for one location.

Source: Open-Meteo Historical Weather API (archive). Free, no API key.
"""

from datetime import date

from app import cache
from app.fetch import fetch_json

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HISTORY_YEARS = 5

# Open-Meteo variable name -> our name (with its unit, to avoid confusion).
DAILY_VARIABLES = {
    "snowfall_sum": "snowfall_cm",
    "precipitation_sum": "precipitation_mm",
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "wind_gusts_10m_max": "wind_gust_max_kmh",
}


def default_period(today=None):
    """The last HISTORY_YEARS full calendar years, e.g. 2021-01-01 to 2025-12-31."""
    today = today or date.today()
    last_year = today.year - 1
    first_year = last_year - HISTORY_YEARS + 1
    return date(first_year, 1, 1), date(last_year, 12, 31)


def fetch_daily_weather(lat, lon, start_date, end_date, db_path=cache.DB_PATH):
    """Return daily weather between two dates (inclusive).

    Example result:
        {"date": ["2025-01-01", ...], "snowfall_cm": [0.0, ...], ...}
    One list per variable, all the same length. Missing values are None.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "auto",
    }
    data = fetch_json(ARCHIVE_URL, params, db_path)
    daily = data["daily"]

    result = {"date": daily["time"]}
    for api_name, our_name in DAILY_VARIABLES.items():
        result[our_name] = daily[api_name]
    return result

"""Tests for the cache and the API clients. No real network calls:
fetch._download is replaced by a fake that returns canned responses."""

from datetime import date

import pytest

from app import cache, fetch, nri, weather


@pytest.fixture
def db(tmp_path):
    """A fresh, empty SQLite file for each test."""
    return tmp_path / "test_cache.db"


@pytest.fixture
def fake_download(monkeypatch):
    """Replace the real HTTP call. Set fake.response, read fake.urls."""

    class FakeDownload:
        response = {}
        urls = []

        def __call__(self, full_url):
            self.urls.append(full_url)
            return self.response

    fake = FakeDownload()
    fake.urls = []
    monkeypatch.setattr(fetch, "_download", fake)
    return fake


# --- cache ---------------------------------------------------------------

def test_cache_returns_none_when_missing(db):
    assert cache.get("missing", db) is None


def test_cache_stores_and_returns_value(db):
    cache.set("key", {"a": [1, 2]}, db)
    assert cache.get("key", db) == {"a": [1, 2]}


# --- fetch ---------------------------------------------------------------

def test_fetch_downloads_once_then_uses_cache(db, fake_download):
    fake_download.response = {"value": 42}
    first = fetch.fetch_json("https://example.com", {"x": 1}, db)
    second = fetch.fetch_json("https://example.com", {"x": 1}, db)
    assert first == second == {"value": 42}
    assert len(fake_download.urls) == 1


def test_fetch_raises_on_api_error_and_does_not_cache_it(db, fake_download):
    fake_download.response = {"error": {"message": "bad request"}}
    with pytest.raises(ValueError):
        fetch.fetch_json("https://example.com", {"x": 1}, db)
    assert cache.get("https://example.com?x=1", db) is None


# --- NRI -----------------------------------------------------------------

def test_nri_extracts_hazard_scores(db, fake_download):
    fake_download.response = {"features": [{"attributes": {
        "COUNTY": "Denver", "STATEABBRV": "CO", "NRI_VER": "December 2025",
        "RISK_SCORE": 95.2, "RISK_RATNG": "Relatively High",
        "HAIL_RISKS": 99.9, "HAIL_RISKR": "Very High",
        "HRCN_RISKS": None, "HRCN_RISKR": "Not Applicable",
    }}]}

    result = nri.fetch_county_risk("08031", db)

    assert result["county"] == "Denver"
    assert result["overall"] == {"score": 95.2, "rating": "Relatively High"}
    assert result["hazards"]["hail"] == {"score": 99.9, "rating": "Very High"}
    assert result["hazards"]["hurricane"]["score"] is None
    assert set(result["hazards"]) == set(nri.NRI_HAZARDS.values())
    assert "STCOFIPS%3D%2708031%27" in fake_download.urls[0]


def test_nri_raises_for_unknown_county(db, fake_download):
    fake_download.response = {"features": []}
    with pytest.raises(ValueError):
        nri.fetch_county_risk("99999", db)


# --- Open-Meteo ----------------------------------------------------------

def test_default_period_is_last_five_full_years():
    assert weather.default_period(date(2026, 11, 25)) == (
        date(2021, 1, 1), date(2025, 12, 31)
    )


def test_weather_renames_variables_with_units(db, fake_download):
    fake_download.response = {"daily": {
        "time": ["2025-01-01", "2025-01-02"],
        "snowfall_sum": [1.4, 0.0],
        "precipitation_sum": [2.0, 0.0],
        "temperature_2m_max": [3.1, 5.0],
        "temperature_2m_min": [-6.0, -2.5],
        "wind_gusts_10m_max": [40.0, 22.3],
    }}

    result = weather.fetch_daily_weather(
        39.74, -104.99, date(2025, 1, 1), date(2025, 1, 2), db
    )

    assert result["date"] == ["2025-01-01", "2025-01-02"]
    assert result["snowfall_cm"] == [1.4, 0.0]
    assert result["wind_gust_max_kmh"] == [40.0, 22.3]
    assert "start_date=2025-01-01" in fake_download.urls[0]

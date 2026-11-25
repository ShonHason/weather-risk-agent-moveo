"""Tests for weather metrics and the risk score, with small fake inputs."""

import pytest

from app import metrics, scoring
from app import scoring_config as config


def fake_daily(days):
    """Build fetch_daily_weather-style data from a list of per-day dicts."""
    variables = ["snowfall_cm", "precipitation_mm", "temp_max_c",
                 "temp_min_c", "wind_gust_max_kmh"]
    daily = {"date": [d["date"] for d in days]}
    for variable in variables:
        daily[variable] = [d.get(variable, 0.0) for d in days]
    return daily


def fake_nri(**percentiles):
    """NRI hazards where every hazard's frequency percentile is 0 unless given."""
    hazards = {name: {"frequency_percentile": 0.0}
               for names in config.CATEGORY_HAZARDS.values() for name in names}
    for name, value in percentiles.items():
        hazards[name]["frequency_percentile"] = value
    return {"hazards": hazards}


def zero_metrics():
    return {"snow_days_per_year": 0, "hot_days_per_year": 0,
            "heavy_rain_days_per_year": 0}


# --- metrics -------------------------------------------------------------

DAYS = [
    {"date": "2024-01-01", "snowfall_cm": 5.0, "temp_min_c": -8.0},
    {"date": "2024-07-01", "temp_max_c": 38.0, "precipitation_mm": 30.0},
    {"date": "2025-01-01", "snowfall_cm": 0.04},         # trace: not a snow day
    {"date": "2025-01-02", "snowfall_cm": 2.0, "wind_gust_max_kmh": 70.0},
    {"date": "2025-06-01", "snowfall_cm": None},         # missing value
    {"date": "2025-06-02"},
]


def test_metrics_counts_events_over_the_whole_period():
    m = metrics.compute_metrics(fake_daily(DAYS))
    assert m["days"] == 6
    assert m["years"] == 2
    assert m["snow_days"] == 2
    assert m["snow_days_per_year"] == 1.0
    assert m["hot_days"] == 1
    assert m["heavy_rain_days"] == 1
    assert m["freezing_days"] == 1
    assert m["windy_days"] == 1
    assert m["total_snowfall_cm"] == 7.0
    assert m["max_wind_gust_kmh"] == 70.0


def test_metrics_for_one_year():
    m = metrics.compute_metrics(fake_daily(DAYS), year=2025)
    assert m["days"] == 4
    assert m["snow_days"] == 1
    assert m["snow_days_pct"] == 25.0
    assert m["period"] == "2025-01-01 to 2025-06-02"


def test_metrics_raises_for_a_year_without_data():
    with pytest.raises(ValueError):
        metrics.compute_metrics(fake_daily(DAYS), year=2019)


# --- scoring -------------------------------------------------------------

def test_nri_category_takes_the_worst_hazard():
    nri = fake_nri(winter_weather=40.0, ice_storm=90.0, cold_wave=0.0)
    score, hazard = scoring.nri_category_score("winter", nri["hazards"])
    assert (score, hazard) == (90.0, "ice_storm")


def test_category_with_no_events_scores_zero():
    nri = fake_nri()
    assert scoring.nri_category_score("hurricane", nri["hazards"]) == (0.0, None)


def test_observed_score_is_linear_and_capped():
    full = config.OBSERVED_SCALES["winter"]["full_score_at"]
    assert scoring.observed_category_score(
        "winter", {"snow_days_per_year": full / 2}) == 50.0
    assert scoring.observed_category_score(
        "winter", {"snow_days_per_year": full * 3}) == 100.0


def test_acute_category_has_no_observed_part():
    assert scoring.observed_category_score("hurricane", zero_metrics()) is None


def test_chronic_category_blends_nri_and_observed():
    full = config.OBSERVED_SCALES["winter"]["full_score_at"]
    hub_metrics = {**zero_metrics(), "snow_days_per_year": full}  # observed 100
    result = scoring.category_score(
        "winter", fake_nri(winter_weather=50.0)["hazards"], hub_metrics)
    assert result["score"] == round(0.7 * 50 + 0.3 * 100, 1)
    assert result["observed_metric"] == "snow_days_per_year"


def test_overall_is_the_weighted_sum_of_categories():
    nri = fake_nri(hurricane=100.0, tornado=50.0)
    result = scoring.risk_score(nri, zero_metrics())
    assert result["categories"]["hurricane"]["score"] == 100.0
    assert result["categories"]["severe_storm"]["score"] == 50.0
    assert result["overall"] == 0.2 * 100 + 0.2 * 50


def test_weights_sum_to_one():
    assert sum(config.CATEGORY_WEIGHTS.values()) == pytest.approx(1.0)


def test_rank_orders_highest_risk_first():
    hubs = [
        {"name": "A", "overall": 30, "categories": {"heat": {"score": 90}}},
        {"name": "B", "overall": 60, "categories": {"heat": {"score": 10}}},
    ]
    assert [h["name"] for h in scoring.rank(hubs)] == ["B", "A"]
    assert [h["name"] for h in scoring.rank(hubs, "heat")] == ["A", "B"]

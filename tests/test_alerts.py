"""Tests for the short-term forecast score and the risk-change alert.
No real API calls: downloads, scores and the outgoing webhook are faked."""

import json

import pytest
from fastapi.testclient import TestClient

from app import alerts, api, cache, fetch, forecast, tools


def make_daily(**columns):
    """A 2-day forecast; every variable is 0 unless given."""
    daily = {"date": ["2026-12-01", "2026-12-02"]}
    for variable in ["snowfall_cm", "precipitation_mm", "wind_gust_max_kmh",
                     "temp_max_c", "temp_min_c"]:
        daily[variable] = columns.get(variable, [0.0, 0.0])
    return daily


def result(hub_id, score):
    """A fake score_hub_forecast() result."""
    return {"hub_id": hub_id, "hub_name": f"{hub_id.title()} Hub", "score": score,
            "hazard": "snow", "date": "2026-12-01", "value": 9.0, "unit": "cm"}


# --- forecast score ---------------------------------------------------------

def test_scale_is_linear_and_capped():
    assert forecast.scale(7.5, 0, 15) == 50.0
    assert forecast.scale(30, 0, 15) == 100.0
    assert forecast.scale(5, 10, 50) == 0.0


def test_scale_works_downwards_for_cold():
    assert forecast.scale(-20, -10, -30) == 50.0
    assert forecast.scale(5, -10, -30) == 0.0


def test_forecast_score_takes_worst_day_then_worst_hazard():
    daily = make_daily(snowfall_cm=[3.0, 12.0], wind_gust_max_kmh=[70.0, 50.0])
    score = forecast.forecast_score(daily)
    assert score["hazard"] == "snow"
    assert score["score"] == 80.0          # 12 cm on a 0-15 scale
    assert score["date"] == "2026-12-02"
    assert score["hazards"]["wind"]["score"] == 50.0   # 70 km/h on 40-100
    assert score["hazards"]["wind"]["date"] == "2026-12-01"


def test_forecast_score_skips_missing_values():
    daily = make_daily(temp_min_c=[None, -25.0])
    score = forecast.forecast_score(daily)
    assert score["hazard"] == "cold"
    assert score["score"] == 75.0


def test_forecast_is_never_cached(tmp_path, monkeypatch):
    db = tmp_path / "cache.db"
    monkeypatch.setattr(fetch, "_download", lambda url: {"value": 1})
    fetch.fetch_json("https://example.com", {"a": 1}, db, use_cache=False)
    assert cache.get("https://example.com?a=1", db) is None


# --- comparing scores -------------------------------------------------------

def test_find_changes_alerts_only_on_big_moves():
    previous = {"chicago": 20.0, "denver": 50.0, "miami": 40.0}
    current = [result("chicago", 35.0), result("denver", 45.0), result("miami", 30.0)]
    changes = alerts.find_changes(previous, current, min_change=10)
    assert [(a["hub_id"], a["change"], a["direction"]) for a in changes] == [
        ("chicago", 15.0, "up"), ("miami", -10.0, "down")]
    assert "Chicago Hub" in changes[0]["message"]


def test_find_changes_new_hub_is_baseline_only():
    assert alerts.find_changes({}, [result("chicago", 90.0)], min_change=10) == []


# --- one check --------------------------------------------------------------

real_run_check = alerts.run_check   # the API tests below replace it


def run(db, scores):
    """Run a check with fixed fake scores per hub."""
    hubs = [{"id": hub_id} for hub_id in scores]
    return real_run_check(db, hubs=hubs,
                            score_fn=lambda hub: result(hub["id"], scores[hub["id"]]))


def test_first_check_is_baseline_then_change_alerts(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    db = tmp_path / "history.db"

    first = run(db, {"chicago": 20.0, "denver": 50.0})
    assert first["alerts"] == []
    assert first["new_baselines"] == ["chicago", "denver"]

    second = run(db, {"chicago": 45.0, "denver": 52.0})
    assert [a["hub_id"] for a in second["alerts"]] == ["chicago"]
    assert second["webhook"] == "not configured"

    saved = alerts.list_alerts(db)
    assert len(saved) == 1 and saved[0]["new_score"] == 45.0


def test_check_compares_with_previous_check(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    db = tmp_path / "history.db"
    run(db, {"chicago": 20.0})
    run(db, {"chicago": 45.0})                       # alert
    third = run(db, {"chicago": 47.0})               # +2 vs last check
    assert third["alerts"] == []


# --- outgoing webhook -------------------------------------------------------

class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_notify_posts_alerts_as_json(monkeypatch):
    sent = []
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.setattr(alerts, "urlopen",
                        lambda request, **kwargs: sent.append(request) or FakeResponse())
    status = alerts.notify([{"hub_id": "chicago"}], "2026-12-01T00:00:00+00:00")
    assert status == "sent"
    assert sent[0].full_url == "https://hooks.example.com/x"
    assert json.loads(sent[0].data)["alerts"] == [{"hub_id": "chicago"}]


def test_notify_failure_does_not_raise(monkeypatch):
    def broken(request, **kwargs):
        raise OSError("connection refused")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.setattr(alerts, "urlopen", broken)
    assert alerts.notify([{"hub_id": "chicago"}], "now").startswith("failed")


def test_notify_sends_nothing_without_alerts(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    assert alerts.notify([], "now") == "nothing to send"


# --- API --------------------------------------------------------------------

http = TestClient(api.app)


@pytest.fixture
def fake_check(tmp_path, monkeypatch):
    """Point the endpoints at a temporary history.db with fake scores."""
    db = tmp_path / "history.db"
    scores = {"chicago": 20.0}
    monkeypatch.setenv("ALERT_TOKEN", "secret")
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(alerts, "run_check", lambda: run(db, scores))
    real_list_alerts = alerts.list_alerts
    monkeypatch.setattr(alerts, "list_alerts",
                        lambda limit: real_list_alerts(db, limit))
    return scores


def test_check_needs_the_token(fake_check):
    assert http.post("/alerts/check").status_code == 401
    assert http.post("/alerts/check", headers={"X-Alert-Token": "wrong"}).status_code == 401


def test_check_refuses_when_token_not_configured(monkeypatch):
    monkeypatch.delenv("ALERT_TOKEN", raising=False)
    assert http.post("/alerts/check", headers={"X-Alert-Token": "x"}).status_code == 503


def test_check_endpoint_baseline_then_alert(fake_check):
    headers = {"X-Alert-Token": "secret"}
    assert http.post("/alerts/check", headers=headers).json()["alerts"] == []

    fake_check["chicago"] = 60.0
    reply = http.post("/alerts/check", headers=headers).json()
    assert reply["alerts"][0]["change"] == 40.0

    listed = http.get("/alerts").json()
    assert listed[0]["hub_id"] == "chicago"


# --- agent tool -------------------------------------------------------------

def test_forecast_tool_returns_score_daily_values_and_scales(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_forecast",
                        lambda lat, lon: make_daily(snowfall_cm=[0.0, 7.5]))
    result = tools.get_forecast_risk("Chicago")
    assert result["hub_id"] == "chicago"
    assert result["score"] == 50.0 and result["hazard"] == "snow"
    assert result["daily"]["snowfall_cm"] == [0.0, 7.5]
    assert "snow" in result["scales"]


def test_forecast_tool_reports_unreachable_api_as_error(monkeypatch):

    def offline(lat, lon):
        raise OSError("network down")
    monkeypatch.setattr(forecast, "fetch_forecast", offline)
    text, is_error = tools.run_tool("get_forecast_risk", {"hub": "Chicago"})
    assert is_error and "unavailable" in text

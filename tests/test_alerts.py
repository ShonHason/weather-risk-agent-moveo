"""Tests for the short-term forecast score and the risk-change alert.
No real API calls: downloads, scores and the outgoing webhook are faked."""

import json
from datetime import datetime, timedelta, timezone

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


# --- forecast vs normal for the hub ----------------------------------------

def history_with(variable, values, month="11"):
    """A fake history: one value per day, all in one calendar month."""
    days = [f"2025-{month}-{(i % 28) + 1:02d}" for i in range(len(values))]
    history = {"date": days}
    for name in ["snowfall_cm", "precipitation_mm", "wind_gust_max_kmh",
                 "temp_max_c", "temp_min_c"]:
        history[name] = values if name == variable else [0.0] * len(values)
    return history


def november_daily(**columns):
    daily = make_daily(**columns)
    daily["date"] = ["2026-11-26", "2026-11-27"]
    return daily


def test_percentile_counts_less_severe_days():
    assert forecast.percentile_in_history(5, [1, 2, 5, 8], lower_is_worse=False) == 50.0
    assert forecast.percentile_in_history(-8, [0, 5, -10, 3], lower_is_worse=True) == 75.0
    assert forecast.percentile_in_history(5, [], lower_is_worse=False) is None


def test_same_frost_counts_in_dallas_not_in_minneapolis():
    daily = november_daily(temp_min_c=[-8.0, 2.0])
    dallas = history_with("temp_min_c", [float(t) for t in range(1, 21)])       # mild Novembers
    minneapolis = history_with("temp_min_c", [float(t) for t in range(-15, 5)])  # cold Novembers
    in_dallas = forecast.forecast_score(daily, dallas)["hazards"]["cold"]
    in_minneapolis = forecast.forecast_score(daily, minneapolis)["hazards"]["cold"]
    assert in_dallas["absolute"] == 0.0 and in_dallas["relative"] == 100.0
    assert in_dallas["score"] == 100.0
    assert in_minneapolis["relative"] == 0.0 and in_minneapolis["score"] == 0.0


def test_relative_starts_at_95th_percentile():
    # 30 mm of rain (disruptive), more than 96 of 100 past days
    past = [0.0] * 96 + [40.0] * 4
    daily = november_daily(precipitation_mm=[30.0, 0.0])
    rain = forecast.forecast_score(daily, history_with("precipitation_mm", past))["hazards"]["heavy_rain"]
    assert rain["percentile"] == 96.0
    assert rain["relative"] == 20.0                  # (96 - 95) / (100 - 95)
    assert rain["score"] == 50.0                     # absolute (30 mm on 10-50) is higher


def test_unusual_but_not_disruptive_is_only_a_note():
    # 14 mm of rain where November is dry: unusual, but under 25 mm
    daily = november_daily(precipitation_mm=[14.0, 0.0])
    score = forecast.forecast_score(daily, history_with("precipitation_mm", [0.0] * 50))
    rain = score["hazards"]["heavy_rain"]
    assert rain["relative"] == 0.0 and rain["score"] == 10.0   # absolute only
    assert [n["hazard"] for n in score["notes"]] == ["heavy_rain"]
    assert "rain 14.0 mm on 2026-11-26 is higher than 100.0% of November" in score["notes"][0]["note"]


def test_no_history_means_absolute_only_and_no_notes():
    score = forecast.forecast_score(november_daily(temp_min_c=[-8.0, 0.0]))
    assert score["hazards"]["cold"]["relative"] == 0.0
    assert score["notes"] == []


# --- comparing scores -------------------------------------------------------

DAY_0 = datetime(2026, 12, 1, 6, 0, tzinfo=timezone.utc)


def day(n):
    """DAY_0 plus n days (n may be a fraction)."""
    return DAY_0 + timedelta(days=n)


def past(score, at_day, alerted=False):
    """One stored score row."""
    return {"score": score, "checked_at": day(at_day).isoformat(), "alerted": alerted,
            "hazard": "wind", "value": 50.0, "unit": "km/h", "date": "2026-11-30"}


def test_compare_with_window_scores_since_last_alert():
    history = [past(10, 0), past(20, 1), past(35, 2, alerted=True), past(40, 3)]
    compared = alerts.past_scores_to_compare(history, now=day(3.5), window_days=3)
    assert [row["score"] for row in compared] == [35, 40]   # from the alert on


def test_compare_drops_scores_older_than_the_window():
    history = [past(10, 0), past(20, 2), past(25, 3)]
    compared = alerts.past_scores_to_compare(history, now=day(4), window_days=3)
    assert [row["score"] for row in compared] == [20, 25]


def test_compare_with_last_check_when_window_is_empty():
    history = [past(10, 0), past(20, 1)]
    compared = alerts.past_scores_to_compare(history, now=day(30), window_days=3)
    assert [row["score"] for row in compared] == [20]


def test_find_changes_uses_the_furthest_past_score():
    changes = alerts.find_changes({"chicago": [past(40, 0), past(45, 1)]},
                                  [result("chicago", 50.0)], min_change=10, min_level=40)
    assert changes[0]["old_score"] == 40 and changes[0]["change"] == 10.0
    assert changes[0]["since"] == day(0).isoformat()
    assert changes[0]["before"]["hazard"] == "wind"      # what drove the old score
    assert changes[0]["now"]["hazard"] == "snow"
    assert "before: wind 50.0 km/h" in changes[0]["message"]


def test_alert_carries_notes_but_notes_never_alert():
    noted = {**result("chicago", 45.0), "notes": [{"note": "Unusual but not disruptive: rain"}]}
    quiet = {**result("denver", 41.0), "notes": [{"note": "Unusual but not disruptive: wind"}]}
    changes = alerts.find_changes({"chicago": [past(30, 0)], "denver": [past(40, 0)]},
                                  [noted, quiet], min_change=10, min_level=40)
    assert [a["hub_id"] for a in changes] == ["chicago"]
    assert changes[0]["notes"] == ["Unusual but not disruptive: rain"]


def test_find_changes_ignores_moves_between_low_scores():
    changes = alerts.find_changes({"minneapolis": [past(14, 0)], "denver": [past(30, 0)]},
                                  [result("minneapolis", 28.0), result("denver", 45.0)],
                                  min_change=10, min_level=40)
    assert [a["hub_id"] for a in changes] == ["denver"]   # 45 reaches the level


def test_find_changes_alerts_on_drops_and_sorts_biggest_first():
    changes = alerts.find_changes(
        {"chicago": [past(50, 0)], "miami": [past(90, 0)], "denver": [past(60, 0)]},
        [result("chicago", 62.0), result("miami", 40.0), result("denver", 62.0)],
        min_change=10, min_level=40)
    assert [(a["hub_id"], a["change"], a["direction"]) for a in changes] == [
        ("miami", -50.0, "down"), ("chicago", 12.0, "up")]


def test_find_changes_new_hub_is_baseline_only():
    assert alerts.find_changes({}, [result("chicago", 90.0)]) == []


# --- one check --------------------------------------------------------------

real_run_check = alerts.run_check   # the API tests below replace it


def run(db, scores, at_day=0):
    """Run a check at DAY_0 + at_day with fixed fake scores per hub."""
    hubs = [{"id": hub_id} for hub_id in scores]
    return real_run_check(db, hubs=hubs, now=day(at_day),
                          score_fn=lambda hub: result(hub["id"], scores[hub["id"]]))


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    return tmp_path / "history.db"


def test_first_check_is_baseline_then_change_alerts(db):
    first = run(db, {"chicago": 40.0, "denver": 50.0})
    assert first["alerts"] == []
    assert first["new_baselines"] == ["chicago", "denver"]

    second = run(db, {"chicago": 65.0, "denver": 52.0}, at_day=0.25)
    assert [a["hub_id"] for a in second["alerts"]] == ["chicago"]
    assert second["webhook"] == "not configured"

    saved = alerts.list_alerts(db)
    assert len(saved) == 1 and saved[0]["new_score"] == 65.0


def test_gradual_rise_alerts_once(db):
    """5 points a day: no single check moves 10, but the window catches it."""
    results = [run(db, {"chicago": score}, at_day=n)
               for n, score in enumerate([40.0, 45.0, 50.0, 55.0, 60.0])]
    alert_days = [n for n, r in enumerate(results) if r["alerts"]]
    assert alert_days == [2, 4]          # 40 -> 50, then 50 -> 60 (not every day)
    assert results[2]["alerts"][0]["old_score"] == 40.0


def test_no_repeat_alert_after_an_alert(db):
    run(db, {"chicago": 40.0})
    assert run(db, {"chicago": 60.0}, at_day=0.5)["alerts"]     # alert
    assert run(db, {"chicago": 62.0}, at_day=1)["alerts"] == []  # still 60ish


# --- outgoing webhook -------------------------------------------------------

class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def sample_alert(old=51.5, new=100.0, before_hazard="snow"):
    """One real alert, built by find_changes."""
    value, unit = {"snow": (9.0, "cm"), "wind": (72.4, "km/h")}[before_hazard]
    before = {**past(old, 0), "hazard": before_hazard, "value": value, "unit": unit,
              "date": "2026-12-01"}
    return alerts.find_changes({"seattle": [before]}, [result("seattle", new)],
                               min_change=10, min_level=40)[0]


def test_summary_text_is_short_and_readable():
    text = alerts.summary_text([sample_alert(before_hazard="wind")])
    assert text.splitlines()[0] == "Weather risk alert (7-day forecast): 1 hub changed"
    # rounded scores, friendly date, no timestamp
    assert ("- Seattle Hub: up Moderate (52) -> Severe (100), "
            "snowfall 9.0 cm on Tue, Dec 1") in text
    assert "T06:00" not in text and "since" not in text


def test_risk_level_bands():
    assert [alerts.risk_level(s) for s in [0, 29.9, 30, 59.9, 60, 80, 100]] == [
        "Low", "Low", "Moderate", "Moderate", "High", "Severe", "Severe"]


def test_summary_text_shows_before_only_when_it_differs():
    same = alerts.summary_text([sample_alert(before_hazard="snow")])
    differs = alerts.summary_text([sample_alert(before_hazard="wind")])
    assert "before" not in same
    assert "(before: wind gusts 72 km/h on Tue, Dec 1)" in differs


def test_notify_posts_text_first_then_full_json(monkeypatch):
    sent = []
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.setattr(alerts, "urlopen",
                        lambda request, **kwargs: sent.append(request) or FakeResponse())
    alert = sample_alert()
    status = alerts.notify([alert], "2026-12-01T00:00:00+00:00")
    assert status == "sent"
    assert sent[0].full_url == "https://hooks.example.com/x"
    body = json.loads(sent[0].data)
    assert list(body) == ["text", "checked_at", "alerts"]
    assert body["text"].startswith("Weather risk alert")
    assert body["alerts"] == [alert]


def test_notify_reports_the_receivers_error(monkeypatch):
    import io
    from urllib.error import HTTPError

    def rejected(request, **kwargs):
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(b"invalid_payload"))
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.setattr(alerts, "urlopen", rejected)
    assert alerts.notify([sample_alert()], "now") == "failed: HTTP 400 invalid_payload"


def test_notify_failure_does_not_raise(monkeypatch):
    def broken(request, **kwargs):
        raise OSError("connection refused")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.setattr(alerts, "urlopen", broken)
    assert alerts.notify([sample_alert()], "now").startswith("failed")


def test_notify_sends_nothing_without_alerts(monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/x")
    assert alerts.notify([], "now") == "nothing to send"


# --- API --------------------------------------------------------------------

http = TestClient(api.app)


@pytest.fixture
def fake_check(tmp_path, monkeypatch):
    """Point the endpoints at a temporary history.db with fake scores."""
    db = tmp_path / "history.db"
    scores = {"chicago": 40.0}
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
    assert reply["alerts"][0]["change"] == 20.0

    listed = http.get("/alerts").json()
    assert listed[0]["hub_id"] == "chicago"


# --- agent tool -------------------------------------------------------------

def test_forecast_tool_returns_score_daily_values_and_scales(monkeypatch):
    monkeypatch.setattr(forecast, "fetch_forecast",
                        lambda lat, lon: make_daily(snowfall_cm=[0.0, 7.5]))
    monkeypatch.setattr(forecast, "fetch_history", lambda lat, lon: None)
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

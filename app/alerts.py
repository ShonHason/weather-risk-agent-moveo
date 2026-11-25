"""Risk-change alert: recompute the short-term scores, compare, notify.

One check (run_check):
  1. compute every hub's short-term score from the forecast (forecast.py);
  2. compare it with the hub's recent scores (see past_scores_to_compare);
  3. at least ALERT_MIN_CHANGE points away from one of them, with the old
     or new score at least ALERT_MIN_LEVEL, is an alert;
  4. save the new scores and the alerts in data/history.db;
  5. if ALERT_WEBHOOK_URL is set, POST the alerts there as JSON.

The first check for a hub only saves a baseline. Scheduling is not done
here: something outside (cron, a cloud scheduler) calls POST /alerts/check.

history.db is separate from the API cache, so deleting cache.db (to refresh
NRI data) keeps the alert history.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import scoring_config as config
from app.fetch import SSL_CONTEXT
from app.forecast import MEASURES, score_hub_forecast
from app.hubs import load_hubs

HISTORY_DB_PATH = Path(__file__).parent.parent / "data" / "history.db"

# The columns of one stored score, in order.
HISTORY_COLUMNS = ["hub_id", "checked_at", "score", "hazard", "value", "unit",
                   "date", "alerted"]


def _connect(db_path):
    connection = sqlite3.connect(db_path)
    # Every hub's short-term score at every check, with what drove it.
    # alerted = 1 when this score raised an alert.
    connection.execute(
        "CREATE TABLE IF NOT EXISTS score_history ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  hub_id TEXT NOT NULL,"
        "  checked_at TEXT NOT NULL,"
        "  score REAL NOT NULL,"
        "  hazard TEXT, value REAL, unit TEXT, date TEXT,"
        "  alerted INTEGER NOT NULL"
        ")"
    )
    # Every alert ever raised, stored as JSON.
    connection.execute(
        "CREATE TABLE IF NOT EXISTS alerts ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  created_at TEXT NOT NULL,"
        "  alert TEXT NOT NULL"
        ")"
    )
    return connection


def past_scores_to_compare(history, now, window_days=None):
    """Which of a hub's past scores a new score is compared with.

    history: the hub's stored scores, oldest first.
    - The scores of the last window_days days, so a gradual rise (5 points
      a day) is caught, not only a jump since the previous check.
    - But only from its last alert on (that alert included), so the same
      change doesn't alert again at every check.
    - No check in the window (e.g. checks were paused): the last check.
    - No history at all: [] (a new hub, the check saves a baseline).
    """
    if window_days is None:
        window_days = config.ALERT_WINDOW_DAYS
    if not history:
        return []
    window_start = now - timedelta(days=window_days)
    recent = [row for row in history
              if datetime.fromisoformat(row["checked_at"]) >= window_start]
    if not recent:
        return [history[-1]]
    alert_positions = [i for i, row in enumerate(recent) if row["alerted"]]
    if alert_positions:
        return recent[alert_positions[-1]:]
    return recent


def find_changes(past_by_hub, current_results, min_change=None, min_level=None):
    """Compare each hub's new score with its past scores; return the alerts.

    past_by_hub: {hub_id: [past score rows]} from past_scores_to_compare.
    current_results: score_hub_forecast() results from this check.
    Alerts are sorted by size of change, biggest first.
    """
    if min_change is None:
        min_change = config.ALERT_MIN_CHANGE
    if min_level is None:
        min_level = config.ALERT_MIN_LEVEL
    alerts = []
    for result in current_results:
        past = past_by_hub.get(result["hub_id"])
        if not past:
            continue   # new hub: baseline only
        # The past score furthest from the new one (oldest if tied).
        before = max(past, key=lambda row: abs(result["score"] - row["score"]))
        change = round(result["score"] - before["score"], 1)
        if abs(change) < min_change:
            continue
        if max(result["score"], before["score"]) < min_level:
            continue   # a move between two low scores
        direction = "up" if change > 0 else "down"
        now_driver = {key: result[key] for key in ("hazard", "value", "unit", "date")}
        before_driver = {key: before[key] for key in ("hazard", "value", "unit", "date")}
        alerts.append({
            "hub_id": result["hub_id"],
            "hub_name": result["hub_name"],
            "old_score": before["score"],
            "new_score": result["score"],
            "old_level": risk_level(before["score"]),
            "new_level": risk_level(result["score"]),
            "change": change,
            "direction": direction,
            "since": before["checked_at"],
            "now": now_driver,
            "before": before_driver,
            # Info only: unusual-but-not-disruptive days (never cause an alert).
            "notes": [note["note"] for note in result.get("notes", [])],
            "message": (
                f"{result['hub_name']}: short-term risk {direction} "
                f"{before['score']} -> {result['score']} since {before['checked_at']} "
                f"(now: {_describe(now_driver)}; before: {_describe(before_driver)})"
            ),
        })
    return sorted(alerts, key=lambda alert: abs(alert["change"]), reverse=True)


def risk_level(score):
    """A score in words: 52 -> 'Moderate' (bands in scoring_config.RISK_LEVELS)."""
    for lowest, level in config.RISK_LEVELS:
        if score >= lowest:
            return level
    return config.RISK_LEVELS[-1][1]


def _describe(driver):
    """'wind 66.6 km/h on 2026-11-27'"""
    return f"{driver['hazard']} {driver['value']} {driver['unit']} on {driver['date']}"


def run_check(db_path=HISTORY_DB_PATH, hubs=None, score_fn=score_hub_forecast,
              now=None):
    """Run one check and return what happened (see module docstring)."""
    hubs = hubs if hubs is not None else load_hubs()
    now = now or datetime.now(timezone.utc)
    checked_at = now.isoformat(timespec="seconds")
    results = [score_fn(hub) for hub in hubs]

    with _connect(db_path) as connection:
        rows = connection.execute(
            f"SELECT {', '.join(HISTORY_COLUMNS)} FROM score_history ORDER BY id"
        ).fetchall()
        history = {}
        for row in rows:
            row = dict(zip(HISTORY_COLUMNS, row))
            history.setdefault(row["hub_id"], []).append(row)

        past_by_hub = {hub_id: past_scores_to_compare(hub_history, now)
                       for hub_id, hub_history in history.items()}
        alerts = find_changes(past_by_hub, results)
        alerted = {alert["hub_id"] for alert in alerts}

        connection.executemany(
            f"INSERT INTO score_history ({', '.join(HISTORY_COLUMNS)})"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(r["hub_id"], checked_at, r["score"], r["hazard"], r["value"],
              r["unit"], r["date"], int(r["hub_id"] in alerted)) for r in results])
        connection.executemany(
            "INSERT INTO alerts (created_at, alert) VALUES (?, ?)",
            [(checked_at, json.dumps(alert)) for alert in alerts])

    return {
        "checked_at": checked_at,
        "hubs_checked": len(results),
        "new_baselines": [r["hub_id"] for r in results if r["hub_id"] not in history],
        "alerts": alerts,
        "webhook": notify(alerts, checked_at),
    }


def notify(alerts, checked_at):
    """POST the alerts to ALERT_WEBHOOK_URL. Returns a short status.

    A failed delivery does not fail the check: the alerts are already
    saved and visible at GET /alerts.
    """
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return "not configured"
    if not alerts:
        return "nothing to send"
    # "text" first: a short summary a person can read (and that Slack
    # displays directly), then the full data for programs.
    body = json.dumps({"text": summary_text(alerts), "checked_at": checked_at,
                       "alerts": alerts}, ensure_ascii=False).encode()
    request = Request(url, data=body, method="POST",
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10, context=SSL_CONTEXT):
            return "sent"
    except HTTPError as error:
        # The receiver's reply says why, e.g. Slack's "invalid_payload".
        reply = error.read().decode(errors="replace")[:200]
        return f"failed: HTTP {error.code} {reply}"
    except OSError as error:   # network errors
        return f"failed: {error}"


def summary_text(alerts):
    """A short, human-readable summary of the alerts, one line per hub.

    Weather risk alert (7-day forecast): 2 hubs changed
    - Seattle Hub: up Moderate (52) -> Severe (100), wind gusts 71 km/h on Thu, Nov 26
    - Buffalo Hub: up Severe (88) -> Severe (100), wind gusts 84 km/h on Thu, Nov 26
      (before: rain 45 mm on Thu, Nov 26)
    """
    count = f"{len(alerts)} hub{'s' if len(alerts) != 1 else ''} changed"
    lines = [f"Weather risk alert (7-day forecast): {count}"]
    for alert in alerts:
        now, before = _driver_text(alert["now"]), _driver_text(alert["before"])
        line = (f"- {alert['hub_name']}: {alert['direction']} "
                f"{alert['old_level']} ({alert['old_score']:.0f}) -> "
                f"{alert['new_level']} ({alert['new_score']:.0f}), {now}")
        if before != now:
            line += f"\n  (before: {before})"
        lines.append(line)
    return "\n".join(lines)


def _driver_text(driver):
    """'wind gusts 71 km/h on Thu, Nov 26'"""
    value = driver["value"]
    value = f"{value:.0f}" if abs(value) >= 10 else f"{value:.1f}"
    return (f"{MEASURES[driver['hazard']]} {value} {driver['unit']} "
            f"on {_friendly_date(driver['date'])}")


def _friendly_date(iso_date):
    """'2026-11-26' -> 'Thu, Nov 26'"""
    day = datetime.strptime(iso_date, "%Y-%m-%d")
    return f"{day:%a, %b} {day.day}"


def list_alerts(db_path=HISTORY_DB_PATH, limit=50):
    """The most recent alerts, newest first."""
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT created_at, alert FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
    return [{"created_at": created_at, **json.loads(alert)}
            for created_at, alert in rows]

"""Risk-change alert: recompute the short-term scores, compare, notify.

One check (run_check):
  1. compute every hub's short-term score from the forecast (forecast.py);
  2. compare with the score saved at the previous check;
  3. a move of at least ALERT_MIN_CHANGE points is an alert;
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
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from app import scoring_config as config
from app.fetch import SSL_CONTEXT
from app.forecast import score_hub_forecast
from app.hubs import load_hubs

HISTORY_DB_PATH = Path(__file__).parent.parent / "data" / "history.db"


def _connect(db_path):
    connection = sqlite3.connect(db_path)
    # The latest short-term score per hub: what the next check compares with.
    connection.execute(
        "CREATE TABLE IF NOT EXISTS forecast_scores ("
        "  hub_id TEXT PRIMARY KEY,"
        "  score REAL NOT NULL,"
        "  checked_at TEXT NOT NULL"
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


def find_changes(previous_scores, current_results, min_change=None):
    """Compare scores and return one alert per hub that moved enough.

    previous_scores: {hub_id: score} from the last check.
    current_results: score_hub_forecast() results from this check.
    A hub missing from previous_scores is new: baseline, no alert.
    """
    if min_change is None:
        min_change = config.ALERT_MIN_CHANGE
    alerts = []
    for result in current_results:
        old = previous_scores.get(result["hub_id"])
        if old is None:
            continue
        change = round(result["score"] - old, 1)
        if abs(change) < min_change:
            continue
        direction = "up" if change > 0 else "down"
        alerts.append({
            "hub_id": result["hub_id"],
            "hub_name": result["hub_name"],
            "old_score": old,
            "new_score": result["score"],
            "change": change,
            "direction": direction,
            "hazard": result["hazard"],
            "date": result["date"],
            "value": result["value"],
            "unit": result["unit"],
            "message": (
                f"{result['hub_name']}: short-term risk {direction} "
                f"{old} -> {result['score']} (worst: {result['hazard']} "
                f"{result['value']} {result['unit']} on {result['date']})"
            ),
        })
    return alerts


def run_check(db_path=HISTORY_DB_PATH, hubs=None, score_fn=score_hub_forecast):
    """Run one check and return what happened (see module docstring)."""
    hubs = hubs if hubs is not None else load_hubs()
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = [score_fn(hub) for hub in hubs]

    with _connect(db_path) as connection:
        previous = dict(connection.execute(
            "SELECT hub_id, score FROM forecast_scores").fetchall())
        alerts = find_changes(previous, results)
        connection.executemany(
            "INSERT OR REPLACE INTO forecast_scores (hub_id, score, checked_at)"
            " VALUES (?, ?, ?)",
            [(r["hub_id"], r["score"], checked_at) for r in results])
        connection.executemany(
            "INSERT INTO alerts (created_at, alert) VALUES (?, ?)",
            [(checked_at, json.dumps(alert)) for alert in alerts])

    return {
        "checked_at": checked_at,
        "hubs_checked": len(results),
        "new_baselines": [r["hub_id"] for r in results if r["hub_id"] not in previous],
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
    body = json.dumps({"checked_at": checked_at, "alerts": alerts}).encode()
    request = Request(url, data=body, method="POST",
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=10, context=SSL_CONTEXT):
            return "sent"
    except OSError as error:   # network errors and HTTP error codes
        return f"failed: {error}"


def list_alerts(db_path=HISTORY_DB_PATH, limit=50):
    """The most recent alerts, newest first."""
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT created_at, alert FROM alerts ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
    return [{"created_at": created_at, **json.loads(alert)}
            for created_at, alert in rows]

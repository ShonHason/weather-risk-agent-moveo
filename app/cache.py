"""A tiny SQLite key-value cache for API responses.

Each response is stored as JSON under its full request URL, so the same
request is only sent to the external API once.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "cache.db"


def _connect(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS api_cache ("
        "  key TEXT PRIMARY KEY,"
        "  value TEXT NOT NULL,"
        "  fetched_at TEXT NOT NULL"
        ")"
    )
    return connection


def get(key, db_path=DB_PATH):
    """Return the cached value for this key, or None if it is not cached."""
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT value FROM api_cache WHERE key = ?", (key,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def set(key, value, db_path=DB_PATH):
    """Store a value (anything JSON-serializable) under this key."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO api_cache (key, value, fetched_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), fetched_at),
        )

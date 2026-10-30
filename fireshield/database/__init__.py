"""Small centralized SQLite event store for FireShield AI.

Records are stored as parameterized rows with JSON details, so the schema stays
small while each existing module keeps its own data contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


EVENT_CATEGORIES = (
    "sensor_reading",
    "camera_detection",
    "risk_assessment",
    "decision_history",
    "suppression_event",
    "operator_override",
)
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "fireshield.db"
_INITIALIZED_PATHS: set[str] = set()


class DatabaseError(RuntimeError):
    """Raised for a SQLite operation failure; callers may retain session data."""


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _iso_timestamp(value: Any = None) -> str:
    if isinstance(value, datetime):
        result = value
    elif value is None:
        result = datetime.now(timezone.utc)
    else:
        try:
            result = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return str(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc).isoformat()


def _connect(path: str | Path | None = None) -> sqlite3.Connection:
    database_path = Path(path) if path is not None else DEFAULT_DATABASE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path), timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(path: str | Path | None = None) -> Path:
    """Create the local database, event table, and query indexes."""
    database_path = Path(path) if path is not None else DEFAULT_DATABASE_PATH
    cache_key = str(database_path.resolve())
    if cache_key in _INITIALIZED_PATHS and database_path.exists():
        return database_path
    try:
        with closing(_connect(database_path)) as connection:
            with connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    category TEXT NOT NULL CHECK (category IN (
                        'sensor_reading', 'camera_detection', 'risk_assessment',
                        'decision_history', 'suppression_event', 'operator_override'
                    )),
                    event_key TEXT NOT NULL UNIQUE,
                    timestamp TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_category_time ON events(category, timestamp DESC)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_events_zone_time ON events(zone_id, timestamp DESC)"
                )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not initialize SQLite database: {exc}") from exc
    _INITIALIZED_PATHS.add(cache_key)
    return database_path


def check_database_connection(path: str | Path | None = None) -> bool:
    """Perform a cheap read-only check without creating or modifying a database."""
    database_path = Path(path) if path is not None else DEFAULT_DATABASE_PATH
    if not database_path.is_file():
        return False
    try:
        connection = sqlite3.connect(
            f"file:{database_path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=1.0,
        )
        try:
            connection.execute("SELECT 1 FROM events LIMIT 1").fetchone()
        finally:
            connection.close()
        return True
    except sqlite3.Error as exc:
        raise DatabaseError(f"SQLite health check failed: {exc}") from exc


def record_event(
    category: str,
    *,
    timestamp: Any = None,
    zone_id: str,
    details: Mapping[str, Any],
    event_key: str | None = None,
    path: str | Path | None = None,
) -> bool:
    """Insert one event, returning False when its stable key already exists."""
    if category not in EVENT_CATEGORIES:
        raise ValueError(f"Unsupported event category: {category}")
    stamp = _iso_timestamp(timestamp)
    zone = str(zone_id or "Unknown zone")
    payload = json.dumps(dict(details), sort_keys=True, separators=(",", ":"), default=_json_default)
    key = event_key or hashlib.sha256(
        f"{category}|{stamp}|{zone}|{payload}".encode("utf-8")
    ).hexdigest()
    try:
        initialize_database(path)
        with closing(_connect(path)) as connection:
            with connection:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO events(category,event_key,timestamp,zone_id,details_json) VALUES(?,?,?,?,?)",
                    (category, key, stamp, zone, payload),
                )
            return cursor.rowcount == 1
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not record {category} event: {exc}") from exc


def recent_events(
    category: str | None = None,
    *,
    zone_id: str | None = None,
    limit: int = 500,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Load recent events; category, zone, and limit are bound SQL parameters."""
    if category is not None and category not in EVENT_CATEGORIES:
        raise ValueError(f"Unsupported event category: {category}")
    if limit < 1:
        return []
    clauses = []
    parameters: list[Any] = []
    if category is not None:
        clauses.append("category = ?")
        parameters.append(category)
    if zone_id is not None:
        clauses.append("zone_id = ?")
        parameters.append(str(zone_id))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = (
        "SELECT category,event_key,timestamp,zone_id,details_json FROM events"
        + where + " ORDER BY timestamp DESC, id DESC LIMIT ?"
    )
    parameters.append(int(limit))
    try:
        initialize_database(path)
        with closing(_connect(path)) as connection:
            rows = connection.execute(query, parameters).fetchall()
        records = []
        for row in rows:
            try:
                details = json.loads(row["details_json"])
            except (TypeError, json.JSONDecodeError):
                details = {}
            records.append({
                **details,
                "category": row["category"],
                "event_key": row["event_key"],
                "timestamp": row["timestamp"],
                "zone": row["zone_id"],
            })
        return records
    except sqlite3.Error as exc:
        raise DatabaseError(f"Could not load recent SQLite events: {exc}") from exc


def load_recent_session_data(
    limit: int = 1200, *, path: str | Path | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Return persisted histories keyed like the existing Streamlit session data."""
    mapping = {
        "sensor_history": "sensor_reading",
        "camera_detection_history": "camera_detection",
        "risk_history": "risk_assessment",
        "decision_history": "decision_history",
        "suppression_event_history": "suppression_event",
        "operator_override_history": "operator_override",
    }
    return {
        target: list(reversed(recent_events(category, limit=limit, path=path)))
        for target, category in mapping.items()
    }


def safe_record_event(*args: Any, **kwargs: Any) -> bool:
    """Best-effort persistence wrapper; logging failures never stop the UI."""
    try:
        return record_event(*args, **kwargs)
    except (DatabaseError, OSError, ValueError):
        return False


__all__ = [
    "DEFAULT_DATABASE_PATH", "DatabaseError", "EVENT_CATEGORIES",
    "initialize_database", "load_recent_session_data", "recent_events",
    "record_event", "safe_record_event", "check_database_connection",
]

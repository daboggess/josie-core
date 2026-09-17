from __future__ import annotations

import contextlib
import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Generator


DEFAULT_MISSIONS_DB = Path(r"D:\Josie\data\missions.db")
DEFAULT_RECEIPTS_DIR = Path(r"D:\Josie\data\mission_receipts")


def now_utc() -> str:
    """Return current UTC timestamp formatted as ISO-8601."""
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_connection(db_path: Path | str, timeout: float = 30.0) -> sqlite3.Connection:
    """Open and configure SQLite connection with WAL, foreign keys, and busy timeout."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = False) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite transactions with automatic commit/rollback."""
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db(db_path: Path | str = DEFAULT_MISSIONS_DB) -> None:
    """Initialize schema for missions and mission events."""
    conn = get_connection(db_path)
    try:
        with transaction(conn, immediate=True):
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    campaign_id TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    status_reason TEXT,
                    metadata_json TEXT
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_events (
                    event_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    details_json TEXT,
                    FOREIGN KEY (mission_id) REFERENCES missions (mission_id) ON DELETE CASCADE
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_missions_campaign_id ON missions(campaign_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_mission_events_mission_id ON mission_events(mission_id);"
            )
    finally:
        conn.close()


def insert_mission(conn: sqlite3.Connection, mission: dict[str, Any]) -> None:
    """Insert a new mission record."""
    plan_json = json.dumps(mission.get("plan") or mission.get("plan_json") or {})
    meta_json = json.dumps(mission.get("metadata") or {})
    conn.execute(
        """
        INSERT INTO missions (
            mission_id, name, objective, status, campaign_id, created_at, updated_at, plan_json, status_reason, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mission["mission_id"],
            mission["name"],
            mission["objective"],
            mission["status"],
            mission.get("campaign_id"),
            mission.get("created_at") or now_utc(),
            mission.get("updated_at") or now_utc(),
            plan_json,
            mission.get("status_reason"),
            meta_json,
        ),
    )


def get_mission(conn: sqlite3.Connection, mission_id: str) -> dict[str, Any] | None:
    """Fetch a mission record by mission_id."""
    cursor = conn.execute("SELECT * FROM missions WHERE mission_id = ?", (mission_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    data = dict(row)
    try:
        data["plan"] = json.loads(data["plan_json"])
    except Exception:
        data["plan"] = {}
    try:
        data["metadata"] = json.loads(data["metadata_json"]) if data.get("metadata_json") else {}
    except Exception:
        data["metadata"] = {}
    return data


def get_mission_by_campaign_id(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any] | None:
    """Fetch a mission record by linked campaign_id."""
    cursor = conn.execute("SELECT * FROM missions WHERE campaign_id = ?", (campaign_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    data = dict(row)
    try:
        data["plan"] = json.loads(data["plan_json"])
    except Exception:
        data["plan"] = {}
    try:
        data["metadata"] = json.loads(data["metadata_json"]) if data.get("metadata_json") else {}
    except Exception:
        data["metadata"] = {}
    return data


def update_mission_status(
    conn: sqlite3.Connection,
    mission_id: str,
    status: str,
    status_reason: str | None = None,
    updated_at: str | None = None,
) -> None:
    """Update mission status and reason."""
    ts = updated_at or now_utc()
    conn.execute(
        """
        UPDATE missions
        SET status = ?, status_reason = ?, updated_at = ?
        WHERE mission_id = ?
        """,
        (status, status_reason, ts, mission_id),
    )


def record_mission_event(
    conn: sqlite3.Connection,
    mission_id: str,
    event_type: str,
    details: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> None:
    """Record an audit event for a mission."""
    ts = created_at or now_utc()
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO mission_events (event_id, mission_id, event_type, created_at, details_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (event_id, mission_id, event_type, ts, json.dumps(details) if details else None),
    )


def list_missions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """List all missions ordered by creation timestamp."""
    cursor = conn.execute("SELECT * FROM missions ORDER BY created_at ASC")
    results: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        data = dict(row)
        try:
            data["plan"] = json.loads(data["plan_json"])
        except Exception:
            data["plan"] = {}
        try:
            data["metadata"] = json.loads(data["metadata_json"]) if data.get("metadata_json") else {}
        except Exception:
            data["metadata"] = {}
        results.append(data)
    return results

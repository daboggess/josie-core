from __future__ import annotations

import contextlib
import datetime as dt
import sqlite3
from pathlib import Path
from typing import Generator


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
    """Context manager for SQLite transactions with automatic commit/rollback.
    
    If immediate=True, issues 'BEGIN IMMEDIATE' to acquire a write lock immediately,
    preventing concurrent writer races.
    """
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

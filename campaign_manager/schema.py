from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    spec_json TEXT,
    runner_id TEXT,
    lease_claimed_at TEXT,
    lease_expires_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    work_order_json TEXT NOT NULL,
    state TEXT NOT NULL,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    attempts_used INTEGER NOT NULL DEFAULT 0,
    retry_safe INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    last_supervisor_request_id TEXT,
    last_supervisor_receipt_id TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    runner_id TEXT,
    claimed_at TEXT,
    lease_expires_at TEXT,
    current_attempt_id TEXT,
    current_supervisor_job_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_campaign ON jobs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_jobs_campaign_state ON jobs(campaign_id, state);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs(state, lease_expires_at);

CREATE TABLE IF NOT EXISTS dependencies (
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    depends_on_job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (campaign_id, job_id, depends_on_job_id)
);

CREATE INDEX IF NOT EXISTS idx_deps_campaign_job ON dependencies(campaign_id, job_id);
CREATE INDEX IF NOT EXISTS idx_deps_depends_on ON dependencies(campaign_id, depends_on_job_id);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    attempt_number INTEGER,
    event_type TEXT NOT NULL,
    state_from TEXT,
    state_to TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_campaign ON events(campaign_id, created_at);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    supervisor_job_id TEXT NOT NULL,
    supervisor_request_id TEXT,
    supervisor_receipt_id TEXT,
    supervisor_receipt_path TEXT,
    status TEXT NOT NULL,
    failure_reason TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_job ON attempts(job_id, attempt_number);
CREATE INDEX IF NOT EXISTS idx_attempts_campaign ON attempts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_attempts_supervisor_job ON attempts(supervisor_job_id);
"""


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """Migrate database from v1 to v2 if columns or tables are missing."""
    # Check campaigns table columns
    cur = conn.execute("PRAGMA table_info(campaigns)")
    camp_cols = {row[1] for row in cur.fetchall()}
    if "runner_id" not in camp_cols:
        conn.execute("ALTER TABLE campaigns ADD COLUMN runner_id TEXT;")
    if "lease_claimed_at" not in camp_cols:
        conn.execute("ALTER TABLE campaigns ADD COLUMN lease_claimed_at TEXT;")
    if "lease_expires_at" not in camp_cols:
        conn.execute("ALTER TABLE campaigns ADD COLUMN lease_expires_at TEXT;")

    # Check jobs table columns
    cur = conn.execute("PRAGMA table_info(jobs)")
    job_cols = {row[1] for row in cur.fetchall()}
    if "current_attempt_id" not in job_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN current_attempt_id TEXT;")
    if "current_supervisor_job_id" not in job_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN current_supervisor_job_id TEXT;")

    # Ensure attempts table exists
    conn.execute("""
    CREATE TABLE IF NOT EXISTS attempts (
        attempt_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
        campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        attempt_number INTEGER NOT NULL,
        supervisor_job_id TEXT NOT NULL,
        supervisor_request_id TEXT,
        supervisor_receipt_id TEXT,
        supervisor_receipt_path TEXT,
        status TEXT NOT NULL,
        failure_reason TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        created_at TEXT NOT NULL
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_job ON attempts(job_id, attempt_number);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_campaign ON attempts(campaign_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_supervisor_job ON attempts(supervisor_job_id);")


def init_db(db_path: Path | str) -> None:
    """Initialize or migrate database schema idempotently.
    
    Safe to call multiple times on existing or new databases.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(path), timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.executescript(SCHEMA_SQL)
        
        # Apply migrations for preexisting databases
        _migrate_to_v2(conn)

        # Check and record migrations
        for v in (1, SCHEMA_VERSION):
            cursor = conn.execute("SELECT version FROM schema_migrations WHERE version = ?", (v,))
            if cursor.fetchone() is None:
                now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (v, now_iso),
                )
        conn.commit()
    finally:
        conn.close()

"""SQLite-backed authoritative project/task state machine."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


TASK_STATES = ("ACTIVE", "WAITING_REVIEW", "BLOCKED", "COMPLETED")
EVENT_TYPES = (
    "task_created",
    "worker_started",
    "worker_completed",
    "review_requested",
    "review_received",
    "blocked",
    "unblocked",
)
UPDATABLE_TASK_FIELDS = frozenset({"title", "assigned_to", "result"})


class BuildBoardError(RuntimeError):
    """Base Build Board error."""


class BlockedTaskError(BuildBoardError):
    """Raised when an operation would advance a blocked task."""


class InvalidTransitionError(BuildBoardError):
    """Raised when a requested state transition is not permitted."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class BuildBoard:
    """Persistent Build Board with database-enforced append-only events."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "BuildBoard":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                title TEXT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('ACTIVE', 'WAITING_REVIEW', 'BLOCKED', 'COMPLETED')
                ),
                assigned_to TEXT,
                requested_review_from TEXT,
                blocker TEXT,
                result TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                task_id TEXT REFERENCES tasks(task_id),
                event_type TEXT NOT NULL CHECK (
                    event_type IN (
                        'task_created', 'worker_started', 'worker_completed',
                        'review_requested', 'review_received', 'blocked', 'unblocked'
                    )
                ),
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS events_append_only_update
            BEFORE UPDATE ON events
            BEGIN
                SELECT RAISE(ABORT, 'events are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS events_append_only_delete
            BEFORE DELETE ON events
            BEGIN
                SELECT RAISE(ABORT, 'events are append-only');
            END;
            """
        )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def create_project(self, project_id: str, name: str, status: str = "ACTIVE") -> dict[str, Any]:
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?)",
                (project_id, name, status, timestamp, timestamp),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return self._row(row)

    def create_task(
        self,
        task_id: str,
        project_id: str,
        title: str,
        *,
        actor: str,
        assigned_to: str | None = None,
    ) -> dict[str, Any]:
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                """INSERT INTO tasks (
                       task_id, project_id, title, status, assigned_to,
                       requested_review_from, blocker, result, created_at, updated_at
                   ) VALUES (?, ?, ?, 'ACTIVE', ?, NULL, NULL, NULL, ?, ?)""",
                (task_id, project_id, title, assigned_to, timestamp, timestamp),
            )
            self._append_event(project_id, task_id, "task_created", actor, {"title": title}, timestamp)
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return self._row(row)

    def update_task(self, task_id: str, **fields: Any) -> dict[str, Any]:
        if not fields or not set(fields).issubset(UPDATABLE_TASK_FIELDS):
            raise ValueError(f"permitted fields are: {', '.join(sorted(UPDATABLE_TASK_FIELDS))}")
        self._require_task(task_id)
        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [fields[field] for field in fields]
        values.extend((self._clock(), task_id))
        with self._connection:
            self._connection.execute(
                f"UPDATE tasks SET {assignments}, updated_at = ? WHERE task_id = ?", values
            )
        return self.get_task(task_id)

    def worker_started(self, task_id: str, *, actor: str) -> dict[str, Any]:
        task = self._require_advancable(task_id)
        if task["status"] != "ACTIVE":
            raise InvalidTransitionError("worker may start only an ACTIVE task")
        with self._connection:
            self._append_event(task["project_id"], task_id, "worker_started", actor, {})
        return self.get_task(task_id)

    def worker_completed(self, task_id: str, *, actor: str, result: str) -> dict[str, Any]:
        task = self._require_advancable(task_id)
        if task["status"] != "ACTIVE":
            raise InvalidTransitionError("worker may complete only an ACTIVE task")
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                "UPDATE tasks SET status = 'COMPLETED', result = ?, updated_at = ? WHERE task_id = ?",
                (result, timestamp, task_id),
            )
            self._append_event(
                task["project_id"], task_id, "worker_completed", actor, {"result": result}, timestamp
            )
        return self.get_task(task_id)

    def request_review(self, task_id: str, *, actor: str, reviewer: str) -> dict[str, Any]:
        task = self._require_advancable(task_id)
        if task["status"] != "ACTIVE":
            raise InvalidTransitionError("review may be requested only for an ACTIVE task")
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                """UPDATE tasks
                   SET status = 'WAITING_REVIEW', requested_review_from = ?, updated_at = ?
                   WHERE task_id = ?""",
                (reviewer, timestamp, task_id),
            )
            self._append_event(
                task["project_id"], task_id, "review_requested", actor, {"reviewer": reviewer}, timestamp
            )
        return self.get_task(task_id)

    def record_review(self, task_id: str, *, actor: str, result: str) -> dict[str, Any]:
        task = self._require_advancable(task_id)
        if task["status"] != "WAITING_REVIEW":
            raise InvalidTransitionError("review may be received only for a WAITING_REVIEW task")
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                """UPDATE tasks
                   SET status = 'ACTIVE', requested_review_from = NULL, result = ?, updated_at = ?
                   WHERE task_id = ?""",
                (result, timestamp, task_id),
            )
            self._append_event(
                task["project_id"], task_id, "review_received", actor, {"result": result}, timestamp
            )
        return self.get_task(task_id)

    def block_task(self, task_id: str, *, actor: str, blocker: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        if task["status"] in ("BLOCKED", "COMPLETED"):
            raise InvalidTransitionError(f"cannot block a {task['status']} task")
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                "UPDATE tasks SET status = 'BLOCKED', blocker = ?, updated_at = ? WHERE task_id = ?",
                (blocker, timestamp, task_id),
            )
            self._append_event(
                task["project_id"], task_id, "blocked", actor,
                {"blocker": blocker, "previous_status": task["status"]}, timestamp,
            )
        return self.get_task(task_id)

    def unblock_task(self, task_id: str, *, actor: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        if task["status"] != "BLOCKED":
            raise InvalidTransitionError("only a BLOCKED task may be unblocked")
        timestamp = self._clock()
        with self._connection:
            self._connection.execute(
                "UPDATE tasks SET status = 'ACTIVE', blocker = NULL, updated_at = ? WHERE task_id = ?",
                (timestamp, task_id),
            )
            self._append_event(task["project_id"], task_id, "unblocked", actor, {}, timestamp)
        return self.get_task(task_id)

    def list_events(self, *, project_id: str | None = None, task_id: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[str] = []
        if project_id is not None:
            clauses.append("project_id = ?")
            values.append(project_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            values.append(task_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"SELECT * FROM events{where} ORDER BY event_id", values
        ).fetchall()
        events = [dict(row) for row in rows]
        for event in events:
            event["payload"] = json.loads(event["payload"])
        return events

    def _require_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _require_advancable(self, task_id: str) -> dict[str, Any]:
        task = self._require_task(task_id)
        if task["status"] == "BLOCKED":
            raise BlockedTaskError("blocked task must be explicitly unblocked before it can advance")
        return task

    def _append_event(
        self,
        project_id: str,
        task_id: str | None,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        timestamp: str | None = None,
    ) -> None:
        self._connection.execute(
            """INSERT INTO events (project_id, task_id, event_type, actor, timestamp, payload)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                task_id,
                event_type,
                actor,
                timestamp or self._clock(),
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )

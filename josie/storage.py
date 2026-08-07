"""Local SQLite persistence for conversations, memories, and task records."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path


class LocalStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    speaker TEXT NOT NULL, content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'complete'))
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'denied'))
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    event TEXT NOT NULL, detail TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def add_message(self, speaker: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT INTO messages(created_at,speaker,content) VALUES (?,?,?)", (self._now(), speaker, content))

    def recent_messages(self, limit: int = 20) -> list[tuple[str, str]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT speaker,content FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [(row["speaker"], row["content"]) for row in reversed(rows)]

    def remember(self, content: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("INSERT INTO memories(created_at,content) VALUES (?,?)", (self._now(), content))
            return int(cursor.lastrowid)

    def memories(self) -> list[tuple[int, str]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id,content FROM memories ORDER BY id").fetchall()
        return [(int(row["id"]), row["content"]) for row in rows]

    def add_task(self, description: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("INSERT INTO tasks(created_at,description) VALUES (?,?)", (self._now(), description))
            return int(cursor.lastrowid)

    def pending_tasks(self) -> list[tuple[int, str]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id,description FROM tasks WHERE status='pending' ORDER BY id").fetchall()
        return [(int(row["id"]), row["description"]) for row in rows]

    def complete_task(self, task_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("UPDATE tasks SET status='complete' WHERE id=? AND status='pending'", (task_id,))
            return cursor.rowcount == 1

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            memories = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            pending = connection.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
            messages = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            approvals = connection.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'").fetchone()[0]
        return {
            "memories": int(memories), "pending_tasks": int(pending),
            "messages": int(messages), "pending_approvals": int(approvals),
        }

    def audit(self, event: str, detail: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit(created_at,event,detail) VALUES (?,?,?)",
                (self._now(), event, detail),
            )

    def recent_activity(self, limit: int = 10) -> list[tuple[str, str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT created_at,event,detail FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [(row["created_at"], row["event"], row["detail"]) for row in rows]

    def request_approval(self, description: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO approvals(created_at,description) VALUES (?,?)",
                (self._now(), description),
            )
            approval_id = int(cursor.lastrowid)
        self.audit("approval_requested", f"{approval_id}: {description}")
        return approval_id

    def pending_approvals(self) -> list[tuple[int, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,description FROM approvals WHERE status='pending' ORDER BY id"
            ).fetchall()
        return [(int(row["id"]), row["description"]) for row in rows]

    def decide_approval(self, approval_id: int, decision: str) -> bool:
        if decision not in {"approved", "denied"}:
            raise ValueError("Decision must be approved or denied")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE approvals SET status=? WHERE id=? AND status='pending'",
                (decision, approval_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit(f"approval_{decision}", str(approval_id))
        return changed

    def create_daily_backup(self, backup_dir: Path, keep: int = 7) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        date_stamp = datetime.now().astimezone().strftime("%Y-%m-%d")
        destination = backup_dir / f"josie-{date_stamp}.db"
        if not destination.exists():
            with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
                source.backup(target)
            self.audit("database_backup", destination.name)
        backups = sorted(backup_dir.glob("josie-????-??-??.db"), reverse=True)
        for old_backup in backups[max(1, keep):]:
            if old_backup.resolve().parent == backup_dir.resolve():
                old_backup.unlink()
        return destination

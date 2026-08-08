"""Local SQLite persistence for conversations, memories, and task records."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, due_at TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'delivered'))
                );
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    basis TEXT NOT NULL CHECK (basis IN ('actual', 'estimated')),
                    category TEXT NOT NULL CHECK (
                        category IN ('revenue', 'expense', 'api_cost', 'electricity', 'savings')
                    ),
                    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provenance_records (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    source TEXT NOT NULL, statement TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unverified'
                    CHECK (status IN ('unverified', 'confirmed', 'rejected'))
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
            reminders = connection.execute("SELECT COUNT(*) FROM reminders WHERE status='pending'").fetchone()[0]
        return {
            "memories": int(memories), "pending_tasks": int(pending),
            "messages": int(messages), "pending_approvals": int(approvals),
            "pending_reminders": int(reminders),
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
            with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(destination)) as target:
                source.backup(target)
            self.audit("database_backup", destination.name)
        backups = sorted(backup_dir.glob("josie-????-??-??.db"), reverse=True)
        for old_backup in backups[max(1, keep):]:
            if old_backup.resolve().parent == backup_dir.resolve():
                old_backup.unlink()
        return destination

    def add_reminder(self, minutes: int, description: str) -> int:
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders(created_at,due_at,description) VALUES (?,?,?)",
                (self._now(), due_at.isoformat(timespec="seconds"), description),
            )
            reminder_id = int(cursor.lastrowid)
        self.audit("reminder_added", f"{reminder_id}: {description}")
        return reminder_id

    def pending_reminders(self) -> list[tuple[int, str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,due_at,description FROM reminders WHERE status='pending' ORDER BY due_at"
            ).fetchall()
        return [(int(row["id"]), row["due_at"], row["description"]) for row in rows]

    def deliver_due_reminders(self) -> list[tuple[int, str]]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,description FROM reminders WHERE status='pending' AND due_at<=? ORDER BY due_at",
                (now,),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE reminders SET status='delivered' WHERE id IN ({placeholders})", ids)
        for reminder_id in ids:
            self.audit("reminder_delivered", str(reminder_id))
        return [(int(row["id"]), row["description"]) for row in rows]

    def record_ledger_entry(
        self, *, basis: str, category: str, amount: str, description: str
    ) -> int:
        if basis not in {"actual", "estimated"}:
            raise ValueError("Ledger basis must be actual or estimated")
        if category not in {"revenue", "expense", "api_cost", "electricity", "savings"}:
            raise ValueError("Unsupported ledger category")
        if category == "savings" and basis != "estimated":
            raise ValueError("Savings must remain estimated and never count as earned money")
        try:
            decimal_amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise ValueError("Amount must be a number") from exc
        if decimal_amount < 0 or decimal_amount > Decimal("1000000000"):
            raise ValueError("Amount is outside the permitted record range")
        cents = int(decimal_amount * 100)
        clean_description = description.strip()
        if not clean_description or len(clean_description) > 500:
            raise ValueError("Description must be between 1 and 500 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO ledger_entries(created_at,basis,category,amount_cents,description) "
                "VALUES (?,?,?,?,?)",
                (self._now(), basis, category, cents, clean_description),
            )
            entry_id = int(cursor.lastrowid)
        self.audit("ledger_recorded", f"{entry_id}: {basis} {category} {cents} cents")
        return entry_id

    def ledger_summary(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT basis,category,COALESCE(SUM(amount_cents),0) total "
                "FROM ledger_entries GROUP BY basis,category"
            ).fetchall()
        totals = {f"{row['basis']}_{row['category']}": int(row["total"]) for row in rows}
        actual_income = totals.get("actual_revenue", 0)
        actual_costs = sum(
            totals.get(f"actual_{category}", 0)
            for category in ("expense", "api_cost", "electricity")
        )
        return {
            "actual_revenue_cents": actual_income,
            "actual_cost_cents": actual_costs,
            "actual_balance_cents": actual_income - actual_costs,
            "estimated_revenue_cents": totals.get("estimated_revenue", 0),
            "estimated_cost_cents": sum(
                totals.get(f"estimated_{category}", 0)
                for category in ("expense", "api_cost", "electricity")
            ),
            "estimated_savings_cents": totals.get("estimated_savings", 0),
        }

    def recent_ledger_entries(self, limit: int = 20) -> list[tuple[int, str, str, int, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,basis,category,amount_cents,description "
                "FROM ledger_entries ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            (int(row["id"]), row["basis"], row["category"], int(row["amount_cents"]), row["description"])
            for row in rows
        ]

    def record_provenance(self, *, source: str, statement: str) -> int:
        clean_source = source.strip()
        clean_statement = statement.strip()
        if not clean_source or len(clean_source) > 100:
            raise ValueError("Source must be between 1 and 100 characters")
        if not clean_statement or len(clean_statement) > 2000:
            raise ValueError("Statement must be between 1 and 2000 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO provenance_records(created_at,source,statement) VALUES (?,?,?)",
                (self._now(), clean_source, clean_statement),
            )
            record_id = int(cursor.lastrowid)
        self.audit("provenance_recorded", f"{record_id}: {clean_source}")
        return record_id

    def provenance_records(self, status: str | None = None) -> list[tuple[int, str, str, str]]:
        if status is not None and status not in {"unverified", "confirmed", "rejected"}:
            raise ValueError("Invalid provenance status")
        query = "SELECT id,source,statement,status FROM provenance_records"
        parameters: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status=?"
            parameters = (status,)
        query += " ORDER BY id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [(int(row["id"]), row["source"], row["statement"], row["status"]) for row in rows]

    def decide_provenance(self, record_id: int, decision: str) -> bool:
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("Decision must be confirmed or rejected")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE provenance_records SET status=? WHERE id=? AND status='unverified'",
                (decision, record_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit(f"provenance_{decision}", str(record_id))
        return changed

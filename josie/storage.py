"""Local SQLite persistence for conversations, memories, and task records."""

from __future__ import annotations

import json
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
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    handler TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','succeeded','failed','review_required')),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL CHECK (max_attempts BETWEEN 1 AND 3),
                    result_json TEXT, last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS repair_proposals (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    job_id INTEGER NOT NULL, failure TEXT NOT NULL,
                    proposal TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'review_required'
                    CHECK (status IN ('review_required','accepted','rejected')),
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                CREATE TABLE IF NOT EXISTS memory_changes (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    memory_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK (action IN ('correct','delete','restore')),
                    replacement_content TEXT,
                    approval_id INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','applied','denied')),
                    applied_at TEXT,
                    original_content TEXT,
                    FOREIGN KEY(memory_id) REFERENCES memories(id),
                    FOREIGN KEY(approval_id) REFERENCES approvals(id)
                );
                CREATE TABLE IF NOT EXISTS model_proposals (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    user_input TEXT NOT NULL, model TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review_required'
                    CHECK (status IN ('review_required','accepted','rejected'))
                );
                CREATE TABLE IF NOT EXISTS external_proposals (
                    id INTEGER PRIMARY KEY, received_at TEXT NOT NULL,
                    external_id TEXT NOT NULL UNIQUE, external_created_at TEXT NOT NULL,
                    source TEXT NOT NULL CHECK (source='openwebui'),
                    kind TEXT NOT NULL CHECK (kind IN ('health_check','memory_export','restore_drill')),
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'review_required'
                    CHECK (status IN ('review_required','accepted','rejected'))
                );
                CREATE TABLE IF NOT EXISTS economic_opportunities (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    title TEXT NOT NULL, source TEXT NOT NULL,
                    estimated_revenue_cents INTEGER NOT NULL
                    CHECK (estimated_revenue_cents >= 0),
                    estimated_cost_cents INTEGER NOT NULL
                    CHECK (estimated_cost_cents >= 0),
                    estimated_hours_milli INTEGER NOT NULL
                    CHECK (estimated_hours_milli > 0),
                    risk TEXT NOT NULL CHECK (risk IN ('low','medium','high')),
                    notes TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'research_only'
                    CHECK (status IN ('research_only','rejected','approved_for_human_review')),
                    external_activity INTEGER NOT NULL DEFAULT 0
                    CHECK (external_activity = 0),
                    action_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (action_authorized = 0)
                );
                CREATE TABLE IF NOT EXISTS hardware_targets (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    component TEXT NOT NULL,
                    target_price_cents INTEGER NOT NULL
                    CHECK (target_price_cents >= 0),
                    expected_capability TEXT NOT NULL,
                    compatibility_status TEXT NOT NULL
                    CHECK (compatibility_status IN ('unknown','needs_review','compatible','incompatible')),
                    notes TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'tracking'
                    CHECK (status IN ('tracking','rejected','acquired')),
                    purchase_authorized INTEGER NOT NULL DEFAULT 0
                    CHECK (purchase_authorized = 0)
                );
                CREATE TABLE IF NOT EXISTS model_handoffs (
                    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                    target TEXT NOT NULL CHECK (target IN ('sophie','bernie')),
                    request TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','answered','cancelled')),
                    response TEXT,
                    answered_at TEXT,
                    api_budget_cents INTEGER NOT NULL DEFAULT 0
                    CHECK (api_budget_cents = 0),
                    manual_relay_required INTEGER NOT NULL DEFAULT 1
                    CHECK (manual_relay_required = 1),
                    external_activity INTEGER NOT NULL DEFAULT 0
                    CHECK (external_activity = 0),
                    response_untrusted INTEGER NOT NULL DEFAULT 1
                    CHECK (response_untrusted = 1)
                );
                CREATE TABLE IF NOT EXISTS learning_units (
                    learning_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    curriculum_version TEXT NOT NULL,
                    unit_digest TEXT NOT NULL,
                    track TEXT NOT NULL,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL
                    CHECK (status IN ('prepared','complete','attention_required')),
                    authority TEXT NOT NULL,
                    budgets_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    claims_json TEXT NOT NULL,
                    contradictions_json TEXT NOT NULL,
                    corrections_json TEXT NOT NULL,
                    assessment_json TEXT NOT NULL,
                    capability_change TEXT NOT NULL DEFAULT 'none'
                    CHECK (capability_change = 'none')
                );
                CREATE TABLE IF NOT EXISTS learning_unit_versions (
                    version_id INTEGER PRIMARY KEY,
                    learning_id TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    curriculum_version TEXT NOT NULL,
                    unit_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    UNIQUE (learning_id, unit_digest),
                    FOREIGN KEY(learning_id) REFERENCES learning_units(learning_id)
                );
                """
            )
            memory_columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(memories)").fetchall()
            }
            if "status" not in memory_columns:
                connection.execute("ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            if "updated_at" not in memory_columns:
                connection.execute("ALTER TABLE memories ADD COLUMN updated_at TEXT")
            for table in ("model_proposals", "external_proposals"):
                proposal_columns = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if "decided_at" not in proposal_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN decided_at TEXT")
                if "decision_reason" not in proposal_columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN decision_reason TEXT")

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
            rows = connection.execute(
                "SELECT id,content FROM memories WHERE status='active' ORDER BY id"
            ).fetchall()
        return [(int(row["id"]), row["content"]) for row in rows]

    def memory_records(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,updated_at,content,status FROM memories ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def request_memory_change(
        self, *, memory_id: int, action: str, replacement_content: str | None = None
    ) -> tuple[int, int]:
        if action not in {"correct", "delete", "restore"}:
            raise ValueError("Memory action must be correct, delete, or restore")
        replacement = replacement_content.strip() if replacement_content is not None else None
        if action == "correct" and (not replacement or len(replacement) > 2_000):
            raise ValueError("A correction must contain between 1 and 2000 characters")
        if action != "correct" and replacement is not None:
            raise ValueError("Only a correction may include replacement content")
        with self._connect() as connection:
            memory = connection.execute(
                "SELECT content,status FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            if memory is None:
                raise ValueError("Memory was not found")
            current_status = str(memory["status"])
            if action in {"correct", "delete"} and current_status != "active":
                raise ValueError("Only an active memory may be corrected or deleted")
            if action == "restore" and current_status != "archived":
                raise ValueError("Only an archived memory may be restored")
            duplicate = connection.execute(
                "SELECT id FROM memory_changes WHERE memory_id=? AND status='pending_review'",
                (memory_id,),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("A memory change is already awaiting review")
            description = f"{action} local memory {memory_id}"
            approval = connection.execute(
                "INSERT INTO approvals(created_at,description) VALUES (?,?)",
                (self._now(), description),
            )
            approval_id = int(approval.lastrowid)
            change = connection.execute(
                "INSERT INTO memory_changes(created_at,memory_id,action,replacement_content,approval_id) "
                "VALUES (?,?,?,?,?)",
                (self._now(), memory_id, action, replacement, approval_id),
            )
            change_id = int(change.lastrowid)
        self.audit("memory_change_requested", f"{change_id}: {action} memory {memory_id}")
        self.audit("approval_requested", f"{approval_id}: {description}")
        return change_id, approval_id

    def memory_changes(self, *, pending_only: bool = False) -> list[dict[str, object]]:
        query = (
            "SELECT c.id,c.memory_id,c.action,c.replacement_content,c.status,c.approval_id,"
            "a.status approval_status FROM memory_changes c "
            "JOIN approvals a ON a.id=c.approval_id"
        )
        if pending_only:
            query += " WHERE c.status='pending_review'"
        query += " ORDER BY c.id"
        with self._connect() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def apply_memory_change(self, change_id: int) -> dict[str, object]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            change = connection.execute(
                "SELECT c.*,a.status approval_status FROM memory_changes c "
                "JOIN approvals a ON a.id=c.approval_id WHERE c.id=?",
                (change_id,),
            ).fetchone()
            if change is None or change["status"] != "pending_review":
                raise ValueError("Pending memory change was not found")
            if change["approval_status"] != "approved":
                raise ValueError("Memory change requires an approved review record")
            memory = connection.execute(
                "SELECT content,status FROM memories WHERE id=?", (change["memory_id"],)
            ).fetchone()
            if memory is None:
                raise ValueError("Memory was not found")
            action = str(change["action"])
            if action == "correct":
                if memory["status"] != "active":
                    raise ValueError("Only an active memory may be corrected")
                connection.execute(
                    "UPDATE memories SET content=?,updated_at=? WHERE id=?",
                    (change["replacement_content"], self._now(), change["memory_id"]),
                )
            elif action == "delete":
                if memory["status"] != "active":
                    raise ValueError("Only an active memory may be deleted")
                connection.execute(
                    "UPDATE memories SET status='archived',updated_at=? WHERE id=?",
                    (self._now(), change["memory_id"]),
                )
            else:
                if memory["status"] != "archived":
                    raise ValueError("Only an archived memory may be restored")
                connection.execute(
                    "UPDATE memories SET status='active',updated_at=? WHERE id=?",
                    (self._now(), change["memory_id"]),
                )
            connection.execute(
                "UPDATE memory_changes SET status='applied',applied_at=?,original_content=? WHERE id=?",
                (self._now(), memory["content"], change_id),
            )
        self.audit("memory_change_applied", f"{change_id}: {action} memory {change['memory_id']}")
        return {
            "change_id": change_id,
            "memory_id": int(change["memory_id"]),
            "action": action,
            "status": "applied",
            "hard_delete": False,
        }

    def record_model_proposal(self, *, user_input: str, model: str, response_json: str) -> int:
        if len(user_input) > 4_000 or len(response_json) > 20_000:
            raise ValueError("Model proposal record is too large")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO model_proposals(created_at,user_input,model,response_json) VALUES (?,?,?,?)",
                (self._now(), user_input, model, response_json),
            )
            proposal_id = int(cursor.lastrowid)
        self.audit("model_proposal_recorded", f"{proposal_id}: {model}")
        return proposal_id

    def recent_model_proposals(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,model,response_json,status,decided_at,decision_reason "
                "FROM model_proposals "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_external_proposal(
        self, *, external_id: str, source: str, kind: str, summary: str,
        external_created_at: str,
    ) -> dict[str, object]:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO external_proposals("
                "received_at,external_id,external_created_at,source,kind,summary"
                ") VALUES (?,?,?,?,?,?)",
                (self._now(), external_id, external_created_at, source, kind, summary),
            )
            inserted = cursor.rowcount == 1
            row = connection.execute(
                "SELECT id FROM external_proposals WHERE external_id=?", (external_id,)
            ).fetchone()
        if inserted:
            self.audit("external_proposal_recorded", f"{row['id']}: {kind}")
        return {"id": int(row["id"]), "inserted": inserted}

    def recent_external_proposals(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,received_at,external_id,source,kind,summary,status,"
                "decided_at,decision_reason "
                "FROM external_proposals ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def decide_proposal(
        self, *, proposal_type: str, proposal_id: int, decision: str, reason: str
    ) -> dict[str, object]:
        tables = {"external": "external_proposals", "model": "model_proposals"}
        if proposal_type not in tables:
            raise ValueError("Proposal type must be external or model")
        statuses = {"accept": "accepted", "reject": "rejected"}
        if decision not in statuses:
            raise ValueError("Decision must be accept or reject")
        clean_reason = reason.strip()
        if not clean_reason or len(clean_reason) > 500:
            raise ValueError("Decision reason must contain 1 to 500 characters")
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE {tables[proposal_type]} "
                "SET status=?,decided_at=?,decision_reason=? "
                "WHERE id=? AND status='review_required'",
                (statuses[decision], self._now(), clean_reason, proposal_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit(
                "proposal_reviewed",
                f"{proposal_type} {proposal_id}: {statuses[decision]}; no execution",
            )
        return {
            "status": statuses[decision] if changed else "not_found_or_already_reviewed",
            "proposal_type": proposal_type,
            "proposal_id": proposal_id,
            "actions_queued": 0,
            "actions_executed": 0,
            "external_activity": False,
        }

    def proposal_review_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            counts: dict[str, dict[str, int]] = {}
            for label, table in (
                ("external", "external_proposals"),
                ("model", "model_proposals"),
                ("repair", "repair_proposals"),
            ):
                rows = connection.execute(
                    f"SELECT status,COUNT(*) total FROM {table} GROUP BY status"
                ).fetchall()
                counts[label] = {str(row["status"]): int(row["total"]) for row in rows}
        return {
            "counts": counts,
            "review_required": sum(
                group.get("review_required", 0) for group in counts.values()
            ),
            "external": self.recent_external_proposals(),
            "model": self.recent_model_proposals(),
            "actions_queued": 0,
            "actions_executed": 0,
        }

    @staticmethod
    def _bounded_handoff_text(value: str, *, label: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 4_000:
            raise ValueError(f"{label} must contain 1 to 4000 characters")
        lowered = clean.lower()
        secret_markers = (
            "sk-", "aizasy", "bearer ", "api_key=", "api-key:",
            "-----begin private key-----", "-----begin rsa private key-----",
        )
        if any(marker in lowered for marker in secret_markers):
            raise ValueError(f"{label} appears to contain a credential")
        return clean

    def create_model_handoff(self, *, target: str, request: str) -> dict[str, object]:
        clean_target = target.strip().lower()
        if clean_target not in {"sophie", "bernie"}:
            raise ValueError("Handoff target must be Sophie or Bernie")
        clean_request = self._bounded_handoff_text(request, label="Handoff request")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO model_handoffs(created_at,target,request) VALUES (?,?,?)",
                (self._now(), clean_target, clean_request),
            )
            handoff_id = int(cursor.lastrowid)
        self.audit("model_handoff_drafted", f"{handoff_id}: {clean_target}")
        return self.model_handoff(handoff_id)

    def model_handoff(self, handoff_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,target,request,status,response,answered_at,"
                "api_budget_cents,manual_relay_required,external_activity,response_untrusted "
                "FROM model_handoffs WHERE id=?", (handoff_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Model handoff was not found")
        record = dict(row)
        for key in ("manual_relay_required", "external_activity", "response_untrusted"):
            record[key] = bool(record[key])
        return record

    def recent_model_handoffs(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,created_at,target,request,status,api_budget_cents,"
                "manual_relay_required,external_activity,response_untrusted "
                "FROM model_handoffs ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()
        records = [dict(row) for row in rows]
        for record in records:
            for key in ("manual_relay_required", "external_activity", "response_untrusted"):
                record[key] = bool(record[key])
        return records

    def record_model_handoff_answer(self, *, handoff_id: int, response: str) -> bool:
        clean_response = self._bounded_handoff_text(response, label="Handoff response")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE model_handoffs SET status='answered',response=?,answered_at=? "
                "WHERE id=? AND status='draft'",
                (clean_response, self._now(), handoff_id),
            )
            changed = cursor.rowcount == 1
        if changed:
            self.audit("model_handoff_answer_recorded", str(handoff_id))
        return changed

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
            learning_units = connection.execute("SELECT COUNT(*) FROM learning_units").fetchone()[0]
            completed_learning_units = connection.execute(
                "SELECT COUNT(*) FROM learning_units WHERE status='complete'"
            ).fetchone()[0]
        return {
            "memories": int(memories), "pending_tasks": int(pending),
            "messages": int(messages), "pending_approvals": int(approvals),
            "pending_reminders": int(reminders),
            "learning_units": int(learning_units),
            "completed_learning_units": int(completed_learning_units),
        }

    @staticmethod
    def _learning_text(value: object, *, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text")
        clean = value.strip()
        if not clean or len(clean) > maximum:
            raise ValueError(f"{label} must contain 1 to {maximum} characters")
        return clean

    def upsert_learning_unit(self, record: dict[str, object]) -> dict[str, object]:
        required = {
            "learning_id", "curriculum_version", "unit_digest", "track", "title",
            "objective", "status", "authority", "budgets", "sources", "evidence",
            "claims", "contradictions", "corrections", "assessment", "capability_change",
        }
        if set(record) != required:
            raise ValueError("Learning unit fields do not match the governed schema")
        learning_id = self._learning_text(
            record["learning_id"], label="Learning ID", maximum=64
        ).upper()
        if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in learning_id):
            raise ValueError("Learning ID contains unsupported characters")
        status = self._learning_text(record["status"], label="Learning status", maximum=32)
        if status not in {"prepared", "complete", "attention_required"}:
            raise ValueError("Learning status is invalid")
        capability_change = self._learning_text(
            record["capability_change"], label="Capability change", maximum=32
        )
        if capability_change != "none":
            raise ValueError("A learning unit cannot grant capability")
        unit_digest = self._learning_text(
            record["unit_digest"], label="Unit digest", maximum=64
        ).lower()
        if len(unit_digest) != 64 or any(character not in "0123456789abcdef" for character in unit_digest):
            raise ValueError("Unit digest must be a SHA-256 value")
        text_fields = {
            "curriculum_version": self._learning_text(
                record["curriculum_version"], label="Curriculum version", maximum=32
            ),
            "track": self._learning_text(record["track"], label="Learning track", maximum=64),
            "title": self._learning_text(record["title"], label="Learning title", maximum=200),
            "objective": self._learning_text(
                record["objective"], label="Learning objective", maximum=1_000
            ),
            "authority": self._learning_text(
                record["authority"], label="Learning authority", maximum=500
            ),
        }
        json_fields: dict[str, str] = {}
        for key in (
            "budgets", "sources", "evidence", "claims", "contradictions",
            "corrections", "assessment",
        ):
            encoded = json.dumps(record[key], separators=(",", ":"), sort_keys=True)
            if len(encoded) > 100_000:
                raise ValueError(f"Learning {key} exceeds the storage limit")
            json_fields[f"{key}_json"] = encoded
        now = self._now()
        version_record = {
            "learning_id": learning_id,
            "curriculum_version": text_fields["curriculum_version"],
            "unit_digest": unit_digest,
            "track": text_fields["track"],
            "title": text_fields["title"],
            "objective": text_fields["objective"],
            "status": status,
            "authority": text_fields["authority"],
            "budgets": record["budgets"],
            "sources": record["sources"],
            "evidence": record["evidence"],
            "claims": record["claims"],
            "contradictions": record["contradictions"],
            "corrections": record["corrections"],
            "assessment": record["assessment"],
            "capability_change": capability_change,
        }
        version_json = json.dumps(version_record, separators=(",", ":"), sort_keys=True)
        if len(version_json) > 500_000:
            raise ValueError("Learning unit version exceeds the storage limit")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT unit_digest,status FROM learning_units WHERE learning_id=?",
                (learning_id,),
            ).fetchone()
            changed = existing is None or (
                str(existing["unit_digest"]) != unit_digest
                or str(existing["status"]) != status
            )
            if changed:
                connection.execute(
                    """
                    INSERT INTO learning_units(
                        learning_id,created_at,updated_at,curriculum_version,unit_digest,
                        track,title,objective,status,authority,budgets_json,sources_json,
                        evidence_json,claims_json,contradictions_json,corrections_json,
                        assessment_json,capability_change
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(learning_id) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        curriculum_version=excluded.curriculum_version,
                        unit_digest=excluded.unit_digest,
                        track=excluded.track,title=excluded.title,objective=excluded.objective,
                        status=excluded.status,authority=excluded.authority,
                        budgets_json=excluded.budgets_json,sources_json=excluded.sources_json,
                        evidence_json=excluded.evidence_json,claims_json=excluded.claims_json,
                        contradictions_json=excluded.contradictions_json,
                        corrections_json=excluded.corrections_json,
                        assessment_json=excluded.assessment_json,
                        capability_change=excluded.capability_change
                    """,
                    (
                        learning_id, now, now, text_fields["curriculum_version"],
                        unit_digest, text_fields["track"], text_fields["title"],
                        text_fields["objective"], status, text_fields["authority"],
                        json_fields["budgets_json"], json_fields["sources_json"],
                        json_fields["evidence_json"], json_fields["claims_json"],
                        json_fields["contradictions_json"], json_fields["corrections_json"],
                        json_fields["assessment_json"], capability_change,
                    ),
                )
            version_cursor = connection.execute(
                "INSERT OR IGNORE INTO learning_unit_versions("
                "learning_id,recorded_at,curriculum_version,unit_digest,status,record_json"
                ") VALUES (?,?,?,?,?,?)",
                (
                    learning_id, now, text_fields["curriculum_version"], unit_digest,
                    status, version_json,
                ),
            )
            version_added = version_cursor.rowcount == 1
        if changed:
            self.audit("learning_unit_synced", f"{learning_id}: {status}")
        elif version_added:
            self.audit("learning_version_backfilled", learning_id)
        return {
            **self.learning_unit(learning_id),
            "changed": changed,
            "version_added": version_added,
        }

    def learning_unit(self, learning_id: str) -> dict[str, object]:
        clean_id = learning_id.strip().upper()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM learning_units WHERE learning_id=?", (clean_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Learning unit was not found")
        record = dict(row)
        for key in (
            "budgets", "sources", "evidence", "claims", "contradictions",
            "corrections", "assessment",
        ):
            record[key] = json.loads(str(record.pop(f"{key}_json")))
        return record

    def learning_units(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            ids = [
                str(row["learning_id"])
                for row in connection.execute(
                    "SELECT learning_id FROM learning_units ORDER BY learning_id"
                ).fetchall()
            ]
        return [self.learning_unit(learning_id) for learning_id in ids]

    def learning_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status,COUNT(*) total FROM learning_units GROUP BY status"
            ).fetchall()
            version_count = int(
                connection.execute("SELECT COUNT(*) FROM learning_unit_versions").fetchone()[0]
            )
        counts = {status: 0 for status in ("prepared", "complete", "attention_required")}
        counts.update({str(row["status"]): int(row["total"]) for row in rows})
        return {
            "status": "ok" if counts["attention_required"] == 0 else "attention_required",
            "units_total": sum(counts.values()),
            "version_records": version_count,
            "units_by_status": counts,
            "capability_change": "none",
            "external_activity": False,
            "api_spending_cents": 0,
            "actions_queued": 0,
            "actions_executed": 0,
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
            if changed and decision == "denied":
                connection.execute(
                    "UPDATE memory_changes SET status='denied' "
                    "WHERE approval_id=? AND status='pending_review'",
                    (approval_id,),
                )
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

    def create_checkpoint_backup(self, backup_dir: Path, label: str = "checkpoint") -> Path:
        clean_label = "".join(character for character in label.lower() if character.isalnum() or character == "-")
        if not clean_label:
            raise ValueError("Checkpoint label is invalid")
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S-%f")
        destination = backup_dir / f"josie-{stamp}-{clean_label}.db"
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        self.audit("database_checkpoint", destination.name)
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

    @staticmethod
    def _research_text(value: str, *, label: str, maximum: int) -> str:
        clean = value.strip()
        if not clean or len(clean) > maximum:
            raise ValueError(f"{label} must contain 1 to {maximum} characters")
        return clean

    def record_economic_opportunity(
        self,
        *,
        title: str,
        source: str,
        estimated_revenue_cents: int,
        estimated_cost_cents: int,
        estimated_hours_milli: int,
        risk: str,
        notes: str,
    ) -> dict[str, object]:
        clean_title = self._research_text(title, label="Title", maximum=200)
        clean_source = self._research_text(source, label="Source", maximum=300)
        clean_notes = self._research_text(notes, label="Notes", maximum=2_000)
        if risk not in {"low", "medium", "high"}:
            raise ValueError("Risk must be low, medium, or high")
        if (
            type(estimated_revenue_cents) is not int
            or type(estimated_cost_cents) is not int
            or min(estimated_revenue_cents, estimated_cost_cents) < 0
        ):
            raise ValueError("Estimated revenue and cost must be non-negative cents")
        if type(estimated_hours_milli) is not int or estimated_hours_milli <= 0:
            raise ValueError("Estimated hours must be positive")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO economic_opportunities("
                "created_at,title,source,estimated_revenue_cents,estimated_cost_cents,"
                "estimated_hours_milli,risk,notes) VALUES (?,?,?,?,?,?,?,?)",
                (
                    self._now(), clean_title, clean_source, estimated_revenue_cents,
                    estimated_cost_cents, estimated_hours_milli, risk, clean_notes,
                ),
            )
            opportunity_id = int(cursor.lastrowid)
        self.audit("opportunity_research_recorded", str(opportunity_id))
        return self.economic_opportunity(opportunity_id)

    def economic_opportunity(self, opportunity_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,title,source,estimated_revenue_cents,"
                "estimated_cost_cents,estimated_hours_milli,risk,notes,status,"
                "external_activity,action_authorized FROM economic_opportunities WHERE id=?",
                (opportunity_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Opportunity was not found")
        result = dict(row)
        profit = int(result["estimated_revenue_cents"]) - int(result["estimated_cost_cents"])
        result["estimated_profit_cents"] = profit
        result["estimated_hourly_profit_cents"] = (
            profit * 1_000 // int(result["estimated_hours_milli"])
        )
        result["external_activity"] = bool(result["external_activity"])
        result["action_authorized"] = bool(result["action_authorized"])
        return result

    def recent_economic_opportunities(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM economic_opportunities ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.economic_opportunity(opportunity_id) for opportunity_id in ids]

    def record_hardware_target(
        self,
        *,
        component: str,
        target_price_cents: int,
        expected_capability: str,
        compatibility_status: str,
        notes: str,
    ) -> dict[str, object]:
        clean_component = self._research_text(component, label="Component", maximum=200)
        clean_capability = self._research_text(
            expected_capability, label="Expected capability", maximum=1_000
        )
        clean_notes = self._research_text(notes, label="Notes", maximum=2_000)
        if type(target_price_cents) is not int or target_price_cents < 0:
            raise ValueError("Target price must be non-negative cents")
        if compatibility_status not in {
            "unknown", "needs_review", "compatible", "incompatible"
        }:
            raise ValueError("Compatibility status is invalid")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO hardware_targets("
                "created_at,component,target_price_cents,expected_capability,"
                "compatibility_status,notes) VALUES (?,?,?,?,?,?)",
                (
                    self._now(), clean_component, target_price_cents,
                    clean_capability, compatibility_status, clean_notes,
                ),
            )
            target_id = int(cursor.lastrowid)
        self.audit("hardware_target_recorded", str(target_id))
        return self.hardware_target(target_id)

    def hardware_target(self, target_id: int) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id,created_at,component,target_price_cents,expected_capability,"
                "compatibility_status,notes,status,purchase_authorized "
                "FROM hardware_targets WHERE id=?",
                (target_id,),
            ).fetchone()
        if row is None:
            raise ValueError("Hardware target was not found")
        result = dict(row)
        result["purchase_authorized"] = bool(result["purchase_authorized"])
        return result

    def recent_hardware_targets(self, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM hardware_targets ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            ]
        return [self.hardware_target(target_id) for target_id in ids]

    def research_summary(self) -> dict[str, object]:
        with self._connect() as connection:
            opportunity_count = int(
                connection.execute("SELECT COUNT(*) FROM economic_opportunities").fetchone()[0]
            )
            hardware_count = int(
                connection.execute("SELECT COUNT(*) FROM hardware_targets").fetchone()[0]
            )
        return {
            "opportunity_count": opportunity_count,
            "hardware_target_count": hardware_count,
            "opportunities": self.recent_economic_opportunities(),
            "hardware_targets": self.recent_hardware_targets(),
            "external_activity": False,
            "transactions_executed": 0,
            "purchases_executed": 0,
            "contracts_accepted": 0,
        }

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

    def enqueue_job(self, handler: str, payload_json: str = "{}", max_attempts: int = 2) -> int:
        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("Job attempts must be between 1 and 3")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO jobs(created_at,handler,payload_json,max_attempts) VALUES (?,?,?,?)",
                (self._now(), handler, payload_json, max_attempts),
            )
            job_id = int(cursor.lastrowid)
        self.audit("job_queued", f"{job_id}: {handler}")
        return job_id

    def claim_next_job(self) -> dict[str, object] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id,handler,payload_json,attempts,max_attempts FROM jobs "
                "WHERE status='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET status='running',attempts=attempts+1 WHERE id=?",
                (row["id"],),
            )
        return {
            "id": int(row["id"]), "handler": row["handler"],
            "payload_json": row["payload_json"], "attempts": int(row["attempts"]) + 1,
            "max_attempts": int(row["max_attempts"]),
        }

    def finish_job(self, job_id: int, result_json: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='succeeded',result_json=?,last_error=NULL "
                "WHERE id=? AND status='running'", (result_json, job_id),
            )
        self.audit("job_succeeded", str(job_id))

    def fail_job(self, job_id: int, error: str) -> str:
        bounded_error = error[:1000]
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempts,max_attempts FROM jobs WHERE id=? AND status='running'", (job_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Running job was not found")
            retry = int(row["attempts"]) < int(row["max_attempts"])
            status = "pending" if retry else "review_required"
            connection.execute(
                "UPDATE jobs SET status=?,last_error=? WHERE id=?", (status, bounded_error, job_id)
            )
            if not retry:
                connection.execute(
                    "INSERT INTO repair_proposals(created_at,job_id,failure,proposal) VALUES (?,?,?,?)",
                    (
                        self._now(), job_id, bounded_error,
                        "Inspect the structured failure and propose a tracked code/config change. "
                        "Do not execute generated code automatically.",
                    ),
                )
        self.audit("job_retry" if retry else "job_review_required", str(job_id))
        return status

    def job_summary(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute("SELECT status,COUNT(*) total FROM jobs GROUP BY status").fetchall()
        result = {status: 0 for status in ("pending", "running", "succeeded", "failed", "review_required")}
        result.update({row["status"]: int(row["total"]) for row in rows})
        return result

    def recent_jobs(self, limit: int = 20) -> list[tuple[int, str, str, int, int]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id,handler,status,attempts,max_attempts FROM jobs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            (int(row["id"]), row["handler"], row["status"], int(row["attempts"]), int(row["max_attempts"]))
            for row in rows
        ]

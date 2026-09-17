from __future__ import annotations

import datetime as dt
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .adapter import RealSupervisorAdapter, SupervisorAdapter
from .constants import (
    DEFAULT_DB_PATH,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_LEASE_GRACE_SECONDS,
    CampaignStatus,
    EventType,
    JobState,
    VALID_JOB_STATES,
)
from .db import get_connection, now_utc, transaction
from .errors import (
    CampaignAlreadyRunningError,
    CampaignNotFoundError,
    InvalidStateTransitionError,
    JobNotFoundError,
    ValidationError,
)
from .models import AttemptRecord, CampaignRecord, EventRecord, JobRecord, SupervisorResult
from .schema import init_db
from .state_machine import validate_transition
from .validation import validate_campaign_spec


def is_lease_stale(lease_expires_at: str | None, now_iso: str | None = None) -> bool:
    """Check if lease timestamp is strictly in the past using timezone-safe UTC comparison.
    
    If lease information is unexpectedly absent or malformed, fail conservatively (return False).
    """
    if not lease_expires_at or not isinstance(lease_expires_at, str) or not lease_expires_at.strip():
        return False
    try:
        lease_dt = dt.datetime.fromisoformat(lease_expires_at)
        if lease_dt.tzinfo is None:
            lease_dt = lease_dt.replace(tzinfo=dt.timezone.utc)
        now_dt = dt.datetime.fromisoformat(now_iso) if now_iso else dt.datetime.now(dt.timezone.utc)
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=dt.timezone.utc)
        return lease_dt < now_dt
    except Exception:
        # Malformed lease: fail conservatively, do not assume dead
        return False


class CampaignManager:
    """Orchestrator for managing campaigns, jobs, dependencies, and execution boundaries."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        adapter: SupervisorAdapter | None = None,
        runner_id: str | None = None,
        lease_duration_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self.db_path = Path(db_path)
        self.runner_id = runner_id or f"runner-{uuid.uuid4().hex[:8]}"
        self.lease_duration = lease_duration_seconds
        init_db(self.db_path)
        if adapter is not None:
            self.adapter = adapter
        else:
            self.adapter = RealSupervisorAdapter()

    def _calculate_job_lease_seconds(self, work_order: dict[str, Any]) -> int:
        """Derive safe execution lease from work-order timeout_seconds + grace period."""
        if "timeout_seconds" in work_order:
            timeout = work_order.get("timeout_seconds", 30)
            sub_attempts = work_order.get("max_attempts", 1)
            return int(timeout * sub_attempts) + DEFAULT_LEASE_GRACE_SECONDS
        return self.lease_duration

    def _get_campaign_record(self, conn: sqlite3.Connection, campaign_id: str) -> CampaignRecord:
        cur = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,))
        row = cur.fetchone()
        if row is None:
            raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")
        return CampaignRecord.from_row(row)

    def acquire_campaign_lease(
        self,
        campaign_id: str,
        min_duration_seconds: int | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        """Atomically acquire execution ownership of a campaign."""
        conn = get_connection(self.db_path)
        now = now_utc()
        duration = lease_seconds or min_duration_seconds or self.lease_duration
        lease_exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=duration)).isoformat()
        try:
            with transaction(conn, immediate=True):
                camp = self._get_campaign_record(conn, campaign_id)
                if camp.runner_id and camp.runner_id != self.runner_id:
                    if not is_lease_stale(camp.lease_expires_at):
                        raise CampaignAlreadyRunningError(
                            f"Campaign '{campaign_id}' is actively running under runner '{camp.runner_id}' "
                            f"(lease expires at {camp.lease_expires_at})"
                        )
                conn.execute(
                    "UPDATE campaigns SET runner_id = ?, lease_claimed_at = ?, lease_expires_at = ?, updated_at = ? "
                    "WHERE campaign_id = ?",
                    (self.runner_id, now, lease_exp, now, campaign_id),
                )
                event_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO events ("
                    "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        campaign_id,
                        "campaign",
                        0,
                        EventType.CAMPAIGN_LEASE_ACQUIRED,
                        camp.status,
                        camp.status,
                        json.dumps({"runner_id": self.runner_id, "lease_expires_at": lease_exp}),
                        now,
                    ),
                )
        finally:
            conn.close()

    def release_campaign_lease(self, campaign_id: str) -> None:
        """Release campaign ownership if held by this runner."""
        conn = get_connection(self.db_path)
        now = now_utc()
        try:
            with transaction(conn, immediate=True):
                cur = conn.execute("SELECT runner_id FROM campaigns WHERE campaign_id = ?", (campaign_id,))
                row = cur.fetchone()
                if row and row["runner_id"] == self.runner_id:
                    conn.execute(
                        "UPDATE campaigns SET runner_id = NULL, lease_claimed_at = NULL, lease_expires_at = NULL, updated_at = ? "
                        "WHERE campaign_id = ?",
                        (now, campaign_id),
                    )
                    event_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO events ("
                        "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            event_id,
                            campaign_id,
                            "campaign",
                            0,
                            EventType.CAMPAIGN_LEASE_RELEASED,
                            None,
                            None,
                            json.dumps({"released_runner_id": self.runner_id}),
                            now,
                        ),
                    )
        finally:
            conn.close()

    def create_campaign(self, spec: dict[str, Any]) -> str:
        """Validate and persist a new campaign atomically."""
        validated = validate_campaign_spec(spec)
        campaign_id = validated.get("campaign_id") or str(uuid.uuid4())
        name = validated["name"]
        now = now_utc()

        conn = get_connection(self.db_path)
        try:
            with transaction(conn, immediate=True):
                # Check for duplicate campaign_id
                cursor = conn.execute("SELECT 1 FROM campaigns WHERE campaign_id = ?", (campaign_id,))
                if cursor.fetchone() is not None:
                    raise ValidationError(f"Campaign with ID '{campaign_id}' already exists")

                conn.execute(
                    "INSERT INTO campaigns (campaign_id, name, created_at, updated_at, status, spec_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (campaign_id, name, now, now, CampaignStatus.QUEUED, json.dumps(spec)),
                )

                for job in validated["jobs"]:
                    job_id = job["job_id"]
                    job_name = job["name"]
                    work_order_json = json.dumps(job["work_order"])
                    initial_state = job.get("initial_state", JobState.QUEUED)
                    max_attempts = job["max_attempts"]
                    retry_safe = 1 if job["retry_safe"] else 0
                    idempotency_key = job.get("idempotency_key") or f"{campaign_id}:{job_id}"

                    conn.execute(
                        "INSERT INTO jobs ("
                        "   job_id, campaign_id, name, work_order_json, state, max_attempts, "
                        "   attempts_used, retry_safe, idempotency_key, failure_reason, created_at, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            job_id,
                            campaign_id,
                            job_name,
                            work_order_json,
                            initial_state,
                            max_attempts,
                            0,
                            retry_safe,
                            idempotency_key,
                            None,
                            now,
                            now,
                        ),
                    )

                    for dep_id in job.get("dependencies", []):
                        conn.execute(
                            "INSERT INTO dependencies (campaign_id, job_id, depends_on_job_id, created_at) "
                            "VALUES (?, ?, ?, ?)",
                            (campaign_id, job_id, dep_id, now),
                        )

                    event_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO events ("
                        "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            event_id,
                            campaign_id,
                            job_id,
                            0,
                            EventType.CAMPAIGN_CREATED,
                            None,
                            initial_state,
                            json.dumps({"name": job_name, "max_attempts": max_attempts, "retry_safe": bool(retry_safe)}),
                            now,
                        ),
                    )
            return campaign_id
        finally:
            conn.close()

    def get_job(self, job_id: str) -> JobRecord:
        """Fetch JobRecord by job_id."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row is None:
                raise JobNotFoundError(f"Job '{job_id}' not found")
            return JobRecord.from_row(row)
        finally:
            conn.close()

    def get_job_events(self, job_id: str) -> list[EventRecord]:
        """Fetch all events for a job."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("SELECT * FROM events WHERE job_id = ? ORDER BY created_at ASC", (job_id,))
            return [EventRecord.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_campaign(self, campaign_id: str) -> CampaignRecord:
        """Fetch CampaignRecord by campaign_id."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,))
            row = cursor.fetchone()
            if row is None:
                raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found")
            return CampaignRecord.from_row(row)
        finally:
            conn.close()

    def get_attempts(self, job_id: str) -> list[AttemptRecord]:
        """Fetch all attempt records for a job."""
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("SELECT * FROM attempts WHERE job_id = ? ORDER BY attempt_number ASC", (job_id,))
            return [AttemptRecord.from_row(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def reconcile(self, campaign_id: str | None = None, force: bool = False) -> list[dict[str, Any]]:
        """Reconcile stale RUNNING jobs against durable supervisor receipts or crash policy.
        
        Automatic reconciliation ONLY acts on a RUNNING job when its execution lease is actually stale/expired.
        An active unexpired RUNNING job remains untouched.
        Receipts are matched against the exact execution-attempt supervisor_job_id.
        """
        conn = get_connection(self.db_path)
        reconciled: list[dict[str, Any]] = []
        now = now_utc()

        try:
            with transaction(conn, immediate=True):
                query = "SELECT * FROM jobs WHERE state = ?"
                params: list[Any] = [JobState.RUNNING]
                if campaign_id:
                    query += " AND campaign_id = ?"
                    params.append(campaign_id)

                cursor = conn.execute(query, params)
                running_jobs = [JobRecord.from_row(row) for row in cursor.fetchall()]

                for job in running_jobs:
                    # DEFECT 1: If lease is not stale and force is False, NEVER reconcile!
                    if not force and not is_lease_stale(job.lease_expires_at):
                        continue

                    work_order = job.work_order
                    receipt_destination = work_order.get("receipt_destination", r"D:\Josie\data\receipts")
                    
                    # DEFECT 3: Look for receipt matching the EXACT execution attempt ID
                    sup_job_id = job.current_supervisor_job_id or job.job_id
                    receipt_pair = self.adapter.find_receipt(receipt_destination, sup_job_id)

                    new_state: str
                    reason: str
                    receipt_id: str | None = None
                    receipt_path: str | None = None

                    if receipt_pair is not None:
                        receipt, rpath = receipt_pair
                        receipt_id = receipt.get("receipt_id") or (rpath.stem if rpath else None)
                        receipt_path = str(rpath) if rpath else None
                        final_status = receipt.get("final_status")
                        receipt_reason = receipt.get("reason", "")

                        if final_status == "PASS":
                            new_state = JobState.PASS
                            reason = receipt_reason or "PASS"
                        elif final_status == "BLOCKED":
                            new_state = JobState.BLOCKED
                            reason = receipt_reason or "BLOCKED"
                        else:
                            # Terminal failure in receipt
                            if job.retry_safe and (job.attempts_used < job.max_attempts):
                                new_state = JobState.RETRY
                                reason = receipt_reason or "FAIL"
                            else:
                                new_state = JobState.FAIL
                                reason = receipt_reason or "FAIL"
                    else:
                        # Outcome is unknown (e.g. process crash before receipt was written)
                        if job.retry_safe and (job.attempts_used < job.max_attempts):
                            new_state = JobState.RETRY
                            reason = "RETRY_AFTER_CRASH"
                        else:
                            new_state = JobState.BLOCKED
                            reason = "UNCERTAIN_EXECUTION"

                    validate_transition(job.state, new_state, job.job_id)

                    completed_at = now if new_state in {JobState.PASS, JobState.FAIL} else None

                    conn.execute(
                        "UPDATE jobs SET "
                        "   state = ?, failure_reason = ?, last_supervisor_receipt_id = COALESCE(?, last_supervisor_receipt_id), "
                        "   runner_id = NULL, claimed_at = NULL, lease_expires_at = NULL, "
                        "   completed_at = COALESCE(?, completed_at), updated_at = ? "
                        "WHERE job_id = ?",
                        (new_state, reason, receipt_id, completed_at, now, job.job_id),
                    )

                    attempt_status = final_status if receipt_pair is not None else (JobState.PASS if new_state == JobState.PASS else JobState.FAIL)
                    # DEFECT 3: Update attempts table if current_attempt_id is present
                    if job.current_attempt_id:
                        conn.execute(
                            "UPDATE attempts SET "
                            "   status = ?, failure_reason = ?, supervisor_receipt_id = ?, "
                            "   supervisor_receipt_path = ?, completed_at = ? "
                            "WHERE attempt_id = ?",
                            (attempt_status, reason, receipt_id, receipt_path, now, job.current_attempt_id),
                        )

                    event_id = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO events ("
                        "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            event_id,
                            job.campaign_id,
                            job.job_id,
                            job.attempts_used,
                            EventType.JOB_RECONCILED,
                            JobState.RUNNING,
                            new_state,
                            json.dumps({
                                "reason": reason,
                                "receipt_id": receipt_id,
                                "receipt_path": receipt_path,
                                "supervisor_job_id": sup_job_id,
                            }),
                            now,
                        ),
                    )

                    reconciled.append({
                        "job_id": job.job_id,
                        "state_from": JobState.RUNNING,
                        "state_to": new_state,
                        "reason": reason,
                        "supervisor_job_id": sup_job_id,
                    })

            return reconciled
        finally:
            conn.close()

    def resolve_dependencies(self, campaign_id: str) -> int:
        """Resolve dependency failures and block dependent jobs when prerequisites permanently fail."""
        conn = get_connection(self.db_path)
        blocked_count = 0
        now = now_utc()

        try:
            with transaction(conn, immediate=True):
                # Fetch all candidates in QUEUED or RETRY
                cursor = conn.execute(
                    "SELECT * FROM jobs WHERE campaign_id = ? AND state IN (?, ?)",
                    (campaign_id, JobState.QUEUED, JobState.RETRY),
                )
                candidates = [JobRecord.from_row(row) for row in cursor.fetchall()]

                for job in candidates:
                    # Check each dependency
                    dep_cursor = conn.execute(
                        "SELECT d.depends_on_job_id, j.state "
                        "FROM dependencies d "
                        "JOIN jobs j ON d.depends_on_job_id = j.job_id "
                        "WHERE d.campaign_id = ? AND d.job_id = ?",
                        (campaign_id, job.job_id),
                    )
                    dep_rows = dep_cursor.fetchall()

                    for dep_id, dep_state in dep_rows:
                        if dep_state in {JobState.FAIL, JobState.CANCELLED, JobState.BLOCKED}:
                            # Prerequisite permanently failed
                            validate_transition(job.state, JobState.BLOCKED, job.job_id)
                            block_reason = f"DEPENDENCY_FAILED: {dep_id} ({dep_state})"

                            conn.execute(
                                "UPDATE jobs SET state = ?, failure_reason = ?, updated_at = ? WHERE job_id = ?",
                                (JobState.BLOCKED, block_reason, now, job.job_id),
                            )

                            event_id = str(uuid.uuid4())
                            conn.execute(
                                "INSERT INTO events ("
                                "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    event_id,
                                    campaign_id,
                                    job.job_id,
                                    job.attempts_used,
                                    EventType.JOB_BLOCKED,
                                    job.state,
                                    JobState.BLOCKED,
                                    json.dumps({"reason": block_reason, "failed_dependency": dep_id}),
                                    now,
                                ),
                            )
                            blocked_count += 1
                            break

            return blocked_count
        finally:
            conn.close()

    def claim_next_job(self, campaign_id: str) -> JobRecord | None:
        """Atomically claim the next runnable job in a campaign.
        
        Enforces:
        1. Single-runner campaign ownership.
        2. At most one executing job in this campaign at any time.
        3. Derived execution lease from work-order timeout.
        4. Durable attempt identity (<job_id>--a<attempt>--<attempt_id>).
        """
        conn = get_connection(self.db_path)
        now = now_utc()
        now_dt = dt.datetime.now(dt.timezone.utc)

        try:
            with transaction(conn, immediate=True):
                # Check campaign lease ownership
                camp = self._get_campaign_record(conn, campaign_id)
                if camp.runner_id and camp.runner_id != self.runner_id:
                    if not is_lease_stale(camp.lease_expires_at):
                        raise CampaignAlreadyRunningError(
                            f"Campaign '{campaign_id}' is leased to runner '{camp.runner_id}' until {camp.lease_expires_at}"
                        )

                # DEFECT 2: Check if ANY job in this campaign is currently RUNNING
                cur = conn.execute(
                    "SELECT count(*) FROM jobs WHERE campaign_id = ? AND state = ?",
                    (campaign_id, JobState.RUNNING),
                )
                if cur.fetchone()[0] > 0:
                    # Strictly sequential per campaign: cannot claim another job while one is running
                    return None

                # Find runnable candidates: state in (RETRY, QUEUED)
                cursor = conn.execute(
                    "SELECT * FROM jobs "
                    "WHERE campaign_id = ? AND state IN (?, ?) "
                    "ORDER BY CASE WHEN state = ? THEN 0 ELSE 1 END, created_at ASC, job_id ASC",
                    (campaign_id, JobState.RETRY, JobState.QUEUED, JobState.RETRY),
                )
                candidates = [JobRecord.from_row(row) for row in cursor.fetchall()]

                for cand in candidates:
                    dep_cursor = conn.execute(
                        "SELECT j.state "
                        "FROM dependencies d "
                        "JOIN jobs j ON d.depends_on_job_id = j.job_id "
                        "WHERE d.campaign_id = ? AND d.job_id = ?",
                        (campaign_id, cand.job_id),
                    )
                    dep_states = [row[0] for row in dep_cursor.fetchall()]

                    if all(state == JobState.PASS for state in dep_states):
                        validate_transition(cand.state, JobState.RUNNING, cand.job_id)
                        new_attempts = cand.attempts_used + 1

                        # Derive safe lease duration from work order timeout
                        lease_seconds = self._calculate_job_lease_seconds(cand.work_order)
                        lease_exp = (now_dt + dt.timedelta(seconds=lease_seconds)).isoformat()

                        # DEFECT 3: Generate attempt ID and execution-specific supervisor_job_id
                        attempt_id = f"att-{uuid.uuid4().hex[:12]}"
                        supervisor_job_id = f"{cand.job_id}--a{new_attempts}--{attempt_id}"

                        conn.execute(
                            "UPDATE jobs SET "
                            "   state = ?, runner_id = ?, claimed_at = ?, lease_expires_at = ?, "
                            "   attempts_used = ?, current_attempt_id = ?, current_supervisor_job_id = ?, "
                            "   started_at = COALESCE(started_at, ?), updated_at = ? "
                            "WHERE job_id = ? AND state IN (?, ?)",
                            (
                                JobState.RUNNING,
                                self.runner_id,
                                now,
                                lease_exp,
                                new_attempts,
                                attempt_id,
                                supervisor_job_id,
                                now,
                                now,
                                cand.job_id,
                                JobState.RETRY,
                                JobState.QUEUED,
                            ),
                        )

                        conn.execute(
                            "INSERT INTO attempts ("
                            "   attempt_id, job_id, campaign_id, attempt_number, supervisor_job_id, "
                            "   status, started_at, created_at"
                            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                attempt_id,
                                cand.job_id,
                                campaign_id,
                                new_attempts,
                                supervisor_job_id,
                                JobState.RUNNING,
                                now,
                                now,
                            ),
                        )

                        # Ensure campaign lease covers at least this job's lease
                        conn.execute(
                            "UPDATE campaigns SET "
                            "   runner_id = ?, lease_claimed_at = COALESCE(lease_claimed_at, ?), "
                            "   lease_expires_at = MAX(COALESCE(lease_expires_at, ?), ?), "
                            "   status = ?, updated_at = ? "
                            "WHERE campaign_id = ?",
                            (
                                self.runner_id,
                                now,
                                lease_exp,
                                lease_exp,
                                CampaignStatus.RUNNING,
                                now,
                                campaign_id,
                            ),
                        )

                        event_id = str(uuid.uuid4())
                        conn.execute(
                            "INSERT INTO events ("
                            "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                event_id,
                                campaign_id,
                                cand.job_id,
                                new_attempts,
                                EventType.JOB_CLAIMED,
                                cand.state,
                                JobState.RUNNING,
                                json.dumps({
                                    "runner_id": self.runner_id,
                                    "lease_expires_at": lease_exp,
                                    "attempt_id": attempt_id,
                                    "supervisor_job_id": supervisor_job_id,
                                }),
                                now,
                            ),
                        )

                        updated_row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (cand.job_id,)).fetchone()
                        return JobRecord.from_row(updated_row)

                return None
        finally:
            conn.close()

    def dispatch_job(self, job: JobRecord) -> SupervisorResult:
        """Submit a claimed job through the Supervisor boundary using execution-specific identity."""
        conn = get_connection(self.db_path)
        req_id = f"req-{uuid.uuid4().hex[:8]}"
        now = now_utc()

        try:
            with transaction(conn, immediate=True):
                conn.execute(
                    "UPDATE jobs SET last_supervisor_request_id = ?, updated_at = ? WHERE job_id = ?",
                    (req_id, now, job.job_id),
                )
                if job.current_attempt_id:
                    conn.execute(
                        "UPDATE attempts SET supervisor_request_id = ? WHERE attempt_id = ?",
                        (req_id, job.current_attempt_id),
                    )
                event_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO events ("
                    "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        job.campaign_id,
                        job.job_id,
                        job.attempts_used,
                        EventType.JOB_DISPATCHED,
                        JobState.RUNNING,
                        JobState.RUNNING,
                        json.dumps({
                            "request_id": req_id,
                            "supervisor_job_id": job.current_supervisor_job_id or job.job_id,
                        }),
                        now,
                    ),
                )
        finally:
            conn.close()

        # DEFECT 3: Dispatch a COPY of the work order using execution-specific supervisor job ID
        work_order_copy = dict(job.work_order)
        if job.current_supervisor_job_id:
            work_order_copy["job_id"] = job.current_supervisor_job_id

        # Execute via adapter outside DB lock
        try:
            result = self.adapter.submit(work_order_copy)
        except Exception as exc:
            result = SupervisorResult(
                final_status="FAIL",
                reason="DISPATCH_EXCEPTION",
                error=str(exc),
            )

        # Consume result and update state using machine evidence
        conn = get_connection(self.db_path)
        now = now_utc()
        try:
            with transaction(conn, immediate=True):
                receipt_dict = result.receipt if isinstance(result.receipt, dict) else None
                receipt_job_id = receipt_dict.get("job_id") if receipt_dict is not None else None

                # A synchronous Supervisor result may produce Campaign Manager PASS ONLY when ALL are true:
                # 1. result.final_status == "PASS"
                # 2. result.receipt is a dict
                # 3. result.receipt.get("final_status") == "PASS"
                # 4. result.receipt.get("job_id") == job.current_supervisor_job_id
                has_machine_pass = (
                    result.final_status == "PASS"
                    and receipt_dict is not None
                    and receipt_dict.get("final_status") == "PASS"
                    and receipt_job_id == job.current_supervisor_job_id
                )

                new_state: str
                failure_reason: str | None = None
                completed_at: str | None = None
                attempt_status: str

                if has_machine_pass:
                    new_state = JobState.PASS
                    completed_at = now
                    attempt_status = JobState.PASS
                elif (
                    result.final_status == "PASS"
                    or (receipt_dict is not None and receipt_dict.get("final_status") == "PASS")
                ) and receipt_job_id != job.current_supervisor_job_id:
                    failure_reason = "RECEIPT_IDENTITY_MISMATCH"
                    if job.retry_safe and (job.attempts_used < job.max_attempts):
                        new_state = JobState.RETRY
                    else:
                        new_state = JobState.FAIL
                        completed_at = now
                    attempt_status = JobState.FAIL
                elif result.final_status == JobState.WAITING_APPROVAL:
                    new_state = JobState.WAITING_APPROVAL
                    failure_reason = result.reason or "WAITING_APPROVAL"
                    attempt_status = JobState.WAITING_APPROVAL
                elif result.final_status == JobState.BLOCKED:
                    new_state = JobState.BLOCKED
                    failure_reason = result.reason or "BLOCKED"
                    attempt_status = JobState.BLOCKED
                else:
                    failure_reason = result.reason or (
                        receipt_dict.get("reason") if receipt_dict else None
                    ) or "EXECUTION_FAILURE"
                    if job.retry_safe and (job.attempts_used < job.max_attempts):
                        new_state = JobState.RETRY
                    else:
                        new_state = JobState.FAIL
                        completed_at = now
                    attempt_status = JobState.FAIL

                validate_transition(JobState.RUNNING, new_state, job.job_id)

                receipt_id = result.receipt_id or (
                    result.receipt.get("receipt_id") if isinstance(result.receipt, dict) else None
                )

                conn.execute(
                    "UPDATE jobs SET "
                    "   state = ?, failure_reason = ?, last_supervisor_receipt_id = COALESCE(?, last_supervisor_receipt_id), "
                    "   runner_id = NULL, claimed_at = NULL, lease_expires_at = NULL, "
                    "   completed_at = COALESCE(?, completed_at), updated_at = ? "
                    "WHERE job_id = ?",
                    (new_state, failure_reason, receipt_id, completed_at, now, job.job_id),
                )
                # DEFECT 3: Update attempts table
                if job.current_attempt_id:
                    conn.execute(
                        "UPDATE attempts SET "
                        "   status = ?, failure_reason = ?, supervisor_receipt_id = ?, "
                        "   supervisor_receipt_path = ?, completed_at = ? "
                        "WHERE attempt_id = ?",
                        (attempt_status, failure_reason, receipt_id, result.receipt_path, now, job.current_attempt_id),
                    )

                event_type_map = {
                    JobState.PASS: EventType.JOB_COMPLETED,
                    JobState.FAIL: EventType.JOB_FAILED,
                    JobState.RETRY: EventType.JOB_RETRYING,
                    JobState.BLOCKED: EventType.JOB_BLOCKED,
                    JobState.WAITING_APPROVAL: EventType.JOB_APPROVAL_REQUESTED,
                }
                event_type = event_type_map.get(new_state, EventType.STATE_TRANSITION)

                event_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO events ("
                    "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        job.campaign_id,
                        job.job_id,
                        job.attempts_used,
                        event_type,
                        JobState.RUNNING,
                        new_state,
                        json.dumps({
                            "reason": failure_reason or "PASS",
                            "receipt_id": receipt_id,
                            "receipt_path": result.receipt_path,
                            "error": result.error,
                            "supervisor_job_id": job.current_supervisor_job_id or job.job_id,
                            "receipt_job_id": receipt_job_id,
                        }),
                        now,
                    ),
                )

            return result
        finally:
            conn.close()

    def run_campaign(self, campaign_id: str) -> dict[str, Any]:
        """Sequential drain loop for a campaign with single-runner ownership."""
        # DEFECT 2: Acquire campaign execution lease
        self.acquire_campaign_lease(campaign_id)
        try:
            # DEFECT 1: Reconcile stale RUNNING jobs
            self.reconcile(campaign_id)

            # Sequential drain loop
            while True:
                # Resolve dependency states
                self.resolve_dependencies(campaign_id)

                # Claim next runnable job (enforces at most one running job in campaign)
                job = self.claim_next_job(campaign_id)
                if job is None:
                    # No runnable work remains
                    break

                # Dispatch through supervisor
                self.dispatch_job(job)

            # Update derived campaign status
            return self._update_campaign_derived_status(campaign_id)
        finally:
            self.release_campaign_lease(campaign_id)

    def _update_campaign_derived_status(self, campaign_id: str) -> dict[str, Any]:
        """Compute and persist derived campaign status based on job outcomes."""
        status_info = self.get_campaign_status(campaign_id)
        counts = status_info["counts"]

        derived_status: str
        if counts[JobState.RUNNING] > 0:
            derived_status = CampaignStatus.RUNNING
        elif counts[JobState.QUEUED] > 0 or counts[JobState.RETRY] > 0:
            if counts[JobState.WAITING_APPROVAL] > 0:
                derived_status = CampaignStatus.BLOCKED
            else:
                derived_status = CampaignStatus.QUEUED
        elif counts[JobState.FAIL] > 0:
            derived_status = CampaignStatus.FAILED
        elif counts[JobState.BLOCKED] > 0 or counts[JobState.WAITING_APPROVAL] > 0:
            derived_status = CampaignStatus.BLOCKED
        elif counts[JobState.CANCELLED] > 0 and counts[JobState.PASS] == 0:
            derived_status = CampaignStatus.CANCELLED
        else:
            derived_status = CampaignStatus.COMPLETED

        conn = get_connection(self.db_path)
        try:
            with transaction(conn, immediate=True):
                conn.execute(
                    "UPDATE campaigns SET status = ?, updated_at = ? WHERE campaign_id = ?",
                    (derived_status, now_utc(), campaign_id),
                )
        finally:
            conn.close()

        status_info["status"] = derived_status
        return status_info

    def get_campaign_status(self, campaign_id: str) -> dict[str, Any]:
        """Retrieve status summary, counts, and job list for a campaign."""
        campaign = self.get_campaign(campaign_id)
        conn = get_connection(self.db_path)
        try:
            cursor = conn.execute("SELECT * FROM jobs WHERE campaign_id = ? ORDER BY created_at ASC, job_id ASC", (campaign_id,))
            jobs = [JobRecord.from_row(row) for row in cursor.fetchall()]

            counts = {state: 0 for state in sorted(list(VALID_JOB_STATES))}
            for job in jobs:
                counts[job.state] = counts.get(job.state, 0) + 1

            summary_order = [
                JobState.PASS,
                JobState.RUNNING,
                JobState.QUEUED,
                JobState.BLOCKED,
                JobState.WAITING_APPROVAL,
                JobState.FAIL,
                JobState.RETRY,
                JobState.CANCELLED,
            ]
            summary_parts = [f"{state} {counts.get(state, 0)}" for state in summary_order]
            summary_str = " | ".join(summary_parts)

            return {
                "campaign_id": campaign.campaign_id,
                "name": campaign.name,
                "status": campaign.status,
                "created_at": campaign.created_at,
                "updated_at": campaign.updated_at,
                "runner_id": campaign.runner_id,
                "lease_claimed_at": campaign.lease_claimed_at,
                "lease_expires_at": campaign.lease_expires_at,
                "counts": counts,
                "summary": summary_str,
                "jobs": [j.to_dict() for j in jobs],
            }
        finally:
            conn.close()

    def approve_job(self, job_id: str) -> JobRecord:
        """Approve a job waiting in WAITING_APPROVAL, transitioning it to QUEUED."""
        job = self.get_job(job_id)
        validate_transition(job.state, JobState.QUEUED, job_id)
        conn = get_connection(self.db_path)
        now = now_utc()
        try:
            with transaction(conn, immediate=True):
                conn.execute(
                    "UPDATE jobs SET state = ?, failure_reason = NULL, updated_at = ? WHERE job_id = ?",
                    (JobState.QUEUED, now, job_id),
                )
                event_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO events ("
                    "   event_id, campaign_id, job_id, attempt_number, event_type, state_from, state_to, details_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        job.campaign_id,
                        job_id,
                        job.attempts_used,
                        EventType.JOB_APPROVED,
                        JobState.WAITING_APPROVAL,
                        JobState.QUEUED,
                        json.dumps({"action": "APPROVED"}),
                        now,
                    ),
                )
            return self.get_job(job_id)
        finally:
            conn.close()

from __future__ import annotations

import datetime as dt
import json
import os
import re
import uuid
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from campaign_manager.constants import CampaignStatus, JobState, VALID_JOB_STATES
from campaign_manager.errors import CampaignNotFoundError, CycleDetectedError, ValidationError
from campaign_manager.manager import CampaignManager

from .db import (
    DEFAULT_MISSIONS_DB,
    DEFAULT_RECEIPTS_DIR,
    get_connection,
    get_mission,
    get_mission_by_campaign_id,
    init_db,
    insert_mission,
    now_utc,
    record_mission_event,
    transaction,
    update_mission_status,
)

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")


class MissionState:
    PLANNED = "PLANNED"
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    VALID_STATES = frozenset({
        PLANNED,
        SUBMITTED,
        RUNNING,
        WAITING_APPROVAL,
        BLOCKED,
        COMPLETED,
        FAILED,
        CANCELLED,
    })

    TERMINAL_STATES = frozenset({
        COMPLETED,
        FAILED,
        BLOCKED,
        CANCELLED,
    })


class BridgeError(Exception):
    """Base error for Mission-Campaign bridge."""
    pass


class MissionValidationError(BridgeError, ValueError):
    """Validation error in mission plan structure or constraints."""
    pass


class MissionNotFoundError(BridgeError, KeyError):
    """Mission ID not found."""
    pass


class BridgeAuthorityError(BridgeError, PermissionError):
    """Authority boundary violation in mission bridge."""
    pass


def _clean_text(val: Any, field_name: str) -> str:
    if not isinstance(val, str) or not val.strip():
        raise MissionValidationError(f"{field_name} must be a non-empty string")
    return val.strip()


def _clean_relative_path(path_val: Any, field_name: str = "allowed path") -> str:
    raw = _clean_text(path_val, field_name).replace("\\", "/")
    if ":" in raw:
        raise MissionValidationError(f"Invalid path (drive letters or colons forbidden): '{raw}'")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or ".." in posix.parts:
        raise MissionValidationError(f"Unsafe relative path '{raw}' in {field_name}")
    normalized = posix.as_posix().lstrip("./")
    if not normalized:
        raise MissionValidationError(f"Empty relative path in {field_name}")
    return normalized


def validate_mission_plan(plan: Any) -> dict[str, Any]:
    """Validate mission plan structure, DAG dependencies, authority constraints, and workspaces.
    
    Raises MissionValidationError if the plan is malformed or invalid.
    """
    if not isinstance(plan, dict):
        raise MissionValidationError("Mission plan must be a JSON object")

    mission_id = _clean_text(plan.get("mission_id"), "mission_id")
    if not ID_PATTERN.fullmatch(mission_id):
        raise MissionValidationError(f"Invalid mission_id '{mission_id}': must match [A-Za-z0-9][A-Za-z0-9_-]{{1,63}}")

    title = plan.get("title") or plan.get("name")
    if not isinstance(title, str) or not title.strip():
        raise MissionValidationError("Mission 'title' or 'name' must be a non-empty string")
    title = title.strip()

    objective = _clean_text(plan.get("objective"), "objective")

    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise MissionValidationError("Mission 'jobs' must be a non-empty list")

    validated_jobs: list[dict[str, Any]] = []
    job_ids: set[str] = set()

    for idx, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            raise MissionValidationError(f"Job at index {idx} must be a JSON object")

        job_id = _clean_text(raw.get("job_id"), f"jobs[{idx}].job_id")
        if not ID_PATTERN.fullmatch(job_id):
            raise MissionValidationError(f"Invalid job_id '{job_id}': must match [A-Za-z0-9][A-Za-z0-9_-]{{1,63}}")
        if job_id in job_ids:
            raise MissionValidationError(f"Duplicate job_id '{job_id}' in mission plan")
        job_ids.add(job_id)

        job_title = raw.get("title") or raw.get("name") or job_id
        if not isinstance(job_title, str) or not job_title.strip():
            raise MissionValidationError(f"Job '{job_id}': title must be a non-empty string")
        job_title = job_title.strip()

        job_objective = _clean_text(raw.get("objective") or (raw.get("work_order", {}) if isinstance(raw.get("work_order"), dict) else {}).get("objective"), f"jobs[{idx}].objective")

        raw_workspace = raw.get("workspace") or (raw.get("work_order", {}) if isinstance(raw.get("work_order"), dict) else {}).get("workspace")
        if not raw_workspace:
            raise MissionValidationError(f"Job '{job_id}': workspace must be specified")
        workspace_path = Path(str(raw_workspace)).resolve()
        if not workspace_path.is_dir():
            raise MissionValidationError(f"Job '{job_id}': workspace must be an existing directory: {workspace_path}")

        # Allowed changes validation
        raw_allowed = raw.get("allowed_changes") or raw.get("allowed_changed_paths") or (raw.get("work_order", {}) if isinstance(raw.get("work_order"), dict) else {}).get("allowed_changed_paths")
        if not isinstance(raw_allowed, list) or not raw_allowed:
            raise MissionValidationError(f"Job '{job_id}': allowed_changes must be a non-empty list")
        allowed_changes = [_clean_relative_path(item, f"Job '{job_id}' allowed change") for item in raw_allowed]

        # Acceptance checks validation
        raw_acceptance = raw.get("acceptance") or (raw.get("work_order", {}) if isinstance(raw.get("work_order"), dict) else {}).get("acceptance")
        if not isinstance(raw_acceptance, list) or not raw_acceptance:
            raise MissionValidationError(f"Job '{job_id}': acceptance must be a non-empty list of check objects")
        acceptance = deepcopy(raw_acceptance)

        # Timeout validation
        raw_timeout = raw.get("timeout_seconds") or raw.get("timeout") or (raw.get("work_order", {}) if isinstance(raw.get("work_order"), dict) else {}).get("timeout_seconds") or 120
        if not isinstance(raw_timeout, (int, float)) or raw_timeout <= 0:
            raise MissionValidationError(f"Job '{job_id}': timeout must be a positive number")
        timeout_seconds = int(raw_timeout)

        # Max attempts validation
        raw_max_attempts = raw.get("max_attempts") or (raw.get("work_order", {}) if isinstance(raw.get("work_order"), dict) else {}).get("max_attempts") or 1
        if not isinstance(raw_max_attempts, int) or raw_max_attempts <= 0:
            raise MissionValidationError(f"Job '{job_id}': max_attempts must be a positive integer")
        max_attempts = int(raw_max_attempts)

        retry_safe = bool(raw.get("retry_safe", True))
        requires_approval = bool(raw.get("requires_approval", False))

        raw_dependencies = raw.get("dependencies", [])
        if not isinstance(raw_dependencies, list) or any(not isinstance(d, str) for d in raw_dependencies):
            raise MissionValidationError(f"Job '{job_id}': dependencies must be a list of strings")
        dependencies = list(dict.fromkeys(raw_dependencies))

        validated_job = {
            "job_id": job_id,
            "title": job_title,
            "name": job_title,
            "objective": job_objective,
            "workspace": str(workspace_path),
            "allowed_changes": allowed_changes,
            "allowed_changed_paths": allowed_changes,
            "acceptance": acceptance,
            "timeout": timeout_seconds,
            "timeout_seconds": timeout_seconds,
            "max_attempts": max_attempts,
            "retry_safe": retry_safe,
            "requires_approval": requires_approval,
            "dependencies": dependencies,
            "department": raw.get("department", "coding"),
        }

        # Pass through any nested work_order or supervisor parameters without modification
        wo = raw.get("work_order") if isinstance(raw.get("work_order"), dict) else {}
        for key in [
            "forbidden_paths", "harness", "model", "prompt_profile", "receipt_destination",
            "agent", "agent_profile", "harness_executable", "harness_config",
            "first_action", "reporting_instructions", "ollama_url", "schema_version"
        ]:
            val = raw.get(key) or wo.get(key)
            if val is not None:
                validated_job[key] = val

        validated_jobs.append(validated_job)

    # Validate dependencies exist
    for job in validated_jobs:
        for dep in job["dependencies"]:
            if dep not in job_ids:
                raise MissionValidationError(f"Job '{job['job_id']}' depends on unknown job '{dep}'")
            if dep == job["job_id"]:
                raise MissionValidationError(f"Job '{job['job_id']}' cannot depend on itself")

    # Detect cycles via DFS
    adj = {j["job_id"]: j["dependencies"] for j in validated_jobs}
    visited: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited
    path: list[str] = []

    def dfs(node: str) -> None:
        visited[node] = 1
        path.append(node)
        for dep in adj.get(node, []):
            st = visited.get(dep, 0)
            if st == 1:
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                raise MissionValidationError(f"Dependency cycle detected: {' -> '.join(cycle)}")
            elif st == 0:
                dfs(dep)
        path.pop()
        visited[node] = 2

    for jid in job_ids:
        if visited.get(jid, 0) == 0:
            dfs(jid)

    return {
        "mission_id": mission_id,
        "title": title,
        "name": title,
        "objective": objective,
        "jobs": validated_jobs,
        "created_at": plan.get("created_at") or now_utc(),
    }


def plan_to_campaign_spec(plan: dict[str, Any]) -> dict[str, Any]:
    """Convert a validated mission plan deterministically into Campaign Manager campaign spec.
    
    Preserves:
    - job identities
    - dependencies DAG
    - retry policy and retry_safe flag
    - work order allowed_changed_paths and acceptance checks
    - approval requirement (JobState.WAITING_APPROVAL)
    """
    validated = validate_mission_plan(plan)
    mission_id = validated["mission_id"]
    campaign_id = f"mission-{mission_id}"
    campaign_name = validated.get("title") or validated.get("name") or mission_id

    campaign_jobs: list[dict[str, Any]] = []
    for job in validated["jobs"]:
        job_id = job["job_id"]
        job_name = job.get("title") or job.get("name") or job_id
        dependencies = list(job.get("dependencies", []))
        max_attempts = int(job.get("max_attempts", 1))
        retry_safe = bool(job.get("retry_safe", True))
        initial_state = JobState.WAITING_APPROVAL if job.get("requires_approval") else JobState.QUEUED
        idempotency_key = f"{campaign_id}:{job_id}"

        work_order: dict[str, Any] = {
            "schema_version": str(job.get("schema_version") or "1"),
            "job_id": job_id,
            "objective": job["objective"],
            "workspace": job["workspace"],
            "harness": str(job.get("harness") or "opencode"),
            "model": str(job.get("model") or "ollama/qwen3:14b"),
            "allowed_changed_paths": list(job["allowed_changes"]),
            "timeout_seconds": int(job["timeout_seconds"]),
            "max_attempts": max_attempts,
            "acceptance": deepcopy(job["acceptance"]),
            "prompt_profile": str(job.get("prompt_profile") or "josie-coder-v1"),
            "receipt_destination": str(job.get("receipt_destination") or r"D:\Josie\data\private\supervisor-local-code"),
        }

        # Pass through authority parameters and worker directives without broadening
        for opt_key in [
            "forbidden_paths", "agent", "agent_profile", "harness_executable",
            "harness_config", "first_action", "reporting_instructions", "ollama_url"
        ]:
            if job.get(opt_key) is not None:
                work_order[opt_key] = job[opt_key]

        campaign_jobs.append({
            "job_id": job_id,
            "name": job_name,
            "work_order": work_order,
            "dependencies": dependencies,
            "max_attempts": max_attempts,
            "retry_safe": retry_safe,
            "initial_state": initial_state,
            "idempotency_key": idempotency_key,
        })

    return {
        "campaign_id": campaign_id,
        "name": campaign_name,
        "jobs": campaign_jobs,
    }


class CampaignBridge:
    """Orchestration bridge connecting Mission Manager to Campaign Manager v0.1.1.
    
    Enforces the architectural boundary:
    Mission Manager plans -> Campaign Bridge adapts -> Campaign Manager orchestrates -> Supervisor authorizes & executes.
    
    The bridge does NOT execute tools directly and does NOT bypass Campaign Manager.
    """

    def __init__(
        self,
        db_path: Path | str = DEFAULT_MISSIONS_DB,
        campaign_manager: CampaignManager | None = None,
        receipt_dir: Path | str = DEFAULT_RECEIPTS_DIR,
    ) -> None:
        self.db_path = Path(db_path)
        self.receipt_dir = Path(receipt_dir)
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        init_db(self.db_path)

        if campaign_manager is None:
            self.campaign_manager = CampaignManager()
        else:
            self.campaign_manager = campaign_manager

    def submit_mission(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Submit a mission plan idempotently into Campaign Manager.
        
        If the mission or linked campaign already exists, reuses the existing campaign without
        creating duplicate records or duplicate side effects.
        """
        validated = validate_mission_plan(plan)
        mission_id = validated["mission_id"]
        campaign_id = f"mission-{mission_id}"

        conn = get_connection(self.db_path)
        try:
            # 1. Check if mission already recorded in missions.db
            existing_mission = get_mission(conn, mission_id)
            if existing_mission is not None:
                record_mission_event(conn, mission_id, "MISSION_SUBMIT_DUPLICATE_IGNORED", {
                    "campaign_id": existing_mission.get("campaign_id")
                })
                conn.commit()
                return self.get_mission_status(mission_id)

            # 2. Check if campaign already exists in Campaign Manager
            try:
                existing_campaign = self.campaign_manager.get_campaign(campaign_id)
                if existing_campaign is not None:
                    # Campaign already exists, persist mission link
                    with transaction(conn, immediate=True):
                        insert_mission(conn, {
                            "mission_id": mission_id,
                            "name": validated["name"],
                            "objective": validated["objective"],
                            "status": MissionState.SUBMITTED,
                            "campaign_id": campaign_id,
                            "plan": validated,
                            "status_reason": "LINKED_TO_EXISTING_CAMPAIGN",
                        })
                        record_mission_event(conn, mission_id, "MISSION_LINKED_TO_EXISTING_CAMPAIGN", {
                            "campaign_id": campaign_id
                        })
                    return self.get_mission_status(mission_id)
            except CampaignNotFoundError:
                pass

            # 3. Fresh submission: convert plan to campaign spec
            campaign_spec = plan_to_campaign_spec(validated)

            # Submit to Campaign Manager
            created_campaign_id = self.campaign_manager.create_campaign(campaign_spec)

            # Persist in missions.db atomically
            with transaction(conn, immediate=True):
                insert_mission(conn, {
                    "mission_id": mission_id,
                    "name": validated["name"],
                    "objective": validated["objective"],
                    "status": MissionState.SUBMITTED,
                    "campaign_id": created_campaign_id,
                    "plan": validated,
                    "status_reason": "CAMPAIGN_SUBMITTED",
                })
                record_mission_event(conn, mission_id, "MISSION_SUBMITTED", {
                    "campaign_id": created_campaign_id
                })

            return self.get_mission_status(mission_id)
        finally:
            conn.close()

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        """Fetch mission record from missions.db."""
        conn = get_connection(self.db_path)
        try:
            record = get_mission(conn, mission_id)
            if record is None:
                raise MissionNotFoundError(f"Mission '{mission_id}' not found")
            return record
        finally:
            conn.close()

    def reconcile_mission(self, mission_id: str) -> dict[str, Any]:
        """Derive mission state strictly from Campaign Manager durable evidence and write receipt if terminal."""
        mission = self.get_mission(mission_id)
        campaign_id = mission.get("campaign_id")
        if not campaign_id:
            return self.get_mission_status(mission_id)

        campaign_status = self.campaign_manager.get_campaign_status(campaign_id)
        counts = campaign_status.get("counts", {})
        c_status = campaign_status.get("status")
        jobs = campaign_status.get("jobs", [])

        # Derive Mission state from Campaign Manager evidence
        mission_state: str
        status_reason: str

        if c_status == CampaignStatus.COMPLETED:
            # Check all jobs in campaign: every required job must be PASS
            all_passed = all(j.get("state") == JobState.PASS for j in jobs) if jobs else False
            if all_passed:
                mission_state = MissionState.COMPLETED
                status_reason = "ALL_JOBS_PASSED_MACHINE_ACCEPTANCE"
            else:
                mission_state = MissionState.FAILED
                status_reason = "CAMPAIGN_COMPLETED_WITH_FAILED_JOBS"
        elif c_status == CampaignStatus.FAILED:
            mission_state = MissionState.FAILED
            status_reason = "CAMPAIGN_FAILED"
        elif c_status == CampaignStatus.CANCELLED:
            mission_state = MissionState.CANCELLED
            status_reason = "CAMPAIGN_CANCELLED"
        elif counts.get(JobState.WAITING_APPROVAL, 0) > 0 and counts.get(JobState.RUNNING, 0) == 0:
            mission_state = MissionState.WAITING_APPROVAL
            status_reason = "WAITING_APPROVAL_GATE"
        elif c_status == CampaignStatus.BLOCKED:
            mission_state = MissionState.BLOCKED
            status_reason = "CAMPAIGN_BLOCKED"
        elif c_status in {CampaignStatus.RUNNING, CampaignStatus.QUEUED}:
            if counts.get(JobState.RUNNING, 0) > 0:
                mission_state = MissionState.RUNNING
                status_reason = "EXECUTION_IN_PROGRESS"
            elif any(counts.get(st, 0) > 0 for st in [JobState.PASS, JobState.FAIL, JobState.RETRY]):
                mission_state = MissionState.RUNNING
                status_reason = "EXECUTION_IN_PROGRESS"
            else:
                mission_state = MissionState.SUBMITTED
                status_reason = "QUEUED_IN_CAMPAIGN"
        else:
            mission_state = MissionState.RUNNING
            status_reason = f"UNKNOWN_CAMPAIGN_STATUS_{c_status}"

        # Persist reconciled state
        conn = get_connection(self.db_path)
        try:
            with transaction(conn, immediate=True):
                update_mission_status(conn, mission_id, mission_state, status_reason)
                record_mission_event(conn, mission_id, "MISSION_RECONCILED", {
                    "mission_state": mission_state,
                    "campaign_status": c_status,
                    "summary": campaign_status.get("summary"),
                })
        finally:
            conn.close()

        # If terminal state, generate and write durable mission receipt
        if mission_state in MissionState.TERMINAL_STATES:
            self._write_mission_receipt(mission_id, mission, campaign_status, mission_state, status_reason)

        return self.get_mission_status(mission_id)

    def _write_mission_receipt(
        self,
        mission_id: str,
        mission: dict[str, Any],
        campaign_status: dict[str, Any],
        final_verdict: str,
        status_reason: str,
    ) -> Path:
        """Write durable JSON mission receipt allowing audit downward to Supervisor receipts."""
        receipt_id = f"rcpt-{mission_id}-{uuid.uuid4().hex[:8]}"
        now = now_utc()
        campaign_id = campaign_status.get("campaign_id")

        job_summaries: list[dict[str, Any]] = []
        supervisor_receipt_ids: list[str] = []

        for j in campaign_status.get("jobs", []):
            job_id = j["job_id"]
            attempts_records: list[dict[str, Any]] = []
            try:
                raw_attempts = self.campaign_manager.get_attempts(job_id)
                attempts_records = [a.to_dict() for a in raw_attempts]
            except Exception:
                attempts_records = []

            for att in attempts_records:
                rcpt_id = att.get("supervisor_receipt_id")
                if rcpt_id and rcpt_id not in supervisor_receipt_ids:
                    supervisor_receipt_ids.append(rcpt_id)

            last_rcpt = j.get("last_supervisor_receipt_id")
            if last_rcpt and last_rcpt not in supervisor_receipt_ids:
                supervisor_receipt_ids.append(last_rcpt)

            job_summaries.append({
                "job_id": job_id,
                "name": j.get("name"),
                "state": j.get("state"),
                "attempts_used": j.get("attempts_used", 0),
                "max_attempts": j.get("max_attempts", 1),
                "last_supervisor_request_id": j.get("last_supervisor_request_id"),
                "last_supervisor_receipt_id": j.get("last_supervisor_receipt_id"),
                "failure_reason": j.get("failure_reason"),
                "attempts": attempts_records,
            })

        receipt_data = {
            "schema_version": "1.0",
            "receipt_id": receipt_id,
            "mission_id": mission_id,
            "campaign_id": campaign_id,
            "created_at": mission.get("created_at"),
            "completed_at": now,
            "final_verdict": final_verdict,
            "status_reason": status_reason,
            "campaign_status": campaign_status.get("status"),
            "summary": campaign_status.get("summary"),
            "counts": campaign_status.get("counts", {}),
            "jobs": job_summaries,
            "audit_trail": {
                "mission_id": mission_id,
                "campaign_id": campaign_id,
                "supervisor_receipt_ids": supervisor_receipt_ids,
            },
        }

        receipt_file = self.receipt_dir / f"{mission_id}.json"
        temp_file = self.receipt_dir / f".{mission_id}.{uuid.uuid4().hex}.tmp"
        try:
            with temp_file.open("w", encoding="utf-8", newline="\n") as f:
                json.dump(receipt_data, f, indent=2, sort_keys=True)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, receipt_file)
        finally:
            if temp_file.exists():
                temp_file.unlink()

        return receipt_file

    def get_mission_status(self, mission_id: str) -> dict[str, Any]:
        """Retrieve full status summary, counts, and jobs for a mission."""
        mission = self.get_mission(mission_id)
        campaign_id = mission.get("campaign_id")

        if campaign_id:
            try:
                c_status = self.campaign_manager.get_campaign_status(campaign_id)
                summary = c_status.get("summary", "")
                counts = c_status.get("counts", {})
                jobs = c_status.get("jobs", [])
                c_state = c_status.get("status")
            except Exception:
                summary = ""
                counts = {}
                jobs = []
                c_state = None
        else:
            summary = ""
            counts = {}
            jobs = []
            c_state = None

        receipt_path = self.receipt_dir / f"{mission_id}.json"

        return {
            "mission_id": mission["mission_id"],
            "name": mission["name"],
            "objective": mission["objective"],
            "status": mission["status"],
            "status_reason": mission.get("status_reason"),
            "campaign_id": campaign_id,
            "campaign_status": c_state,
            "summary": summary,
            "counts": counts,
            "jobs": jobs,
            "created_at": mission.get("created_at"),
            "updated_at": mission.get("updated_at"),
            "receipt_path": str(receipt_path) if receipt_path.exists() else None,
        }

    def render_mission_summary(self, mission_id: str) -> str:
        """Render a single-line human-readable mission status summary."""
        status = self.get_mission_status(mission_id)
        m_id = status["mission_id"]
        m_state = status["status"]
        c_id = status.get("campaign_id") or "UNSUBMITTED"
        c_state = status.get("campaign_status") or "UNKNOWN"
        summary = status.get("summary") or "NO_COUNTS"
        return f"Mission {m_id} ({m_state}) | Campaign {c_id} ({c_state}) | {summary}"

    def get_mission_receipt(self, mission_id: str) -> dict[str, Any]:
        """Fetch durable mission receipt from disk, reconciling first if not yet written."""
        receipt_path = self.receipt_dir / f"{mission_id}.json"
        if not receipt_path.exists():
            self.reconcile_mission(mission_id)
        if not receipt_path.exists():
            raise FileNotFoundError(f"Receipt for mission '{mission_id}' not found at {receipt_path}")
        return json.loads(receipt_path.read_text(encoding="utf-8"))

    def run_mission(self, mission_id: str) -> dict[str, Any]:
        """Run the underlying campaign through Campaign Manager and reconcile the mission."""
        mission = self.get_mission(mission_id)
        campaign_id = mission.get("campaign_id")
        if not campaign_id:
            raise BridgeError(f"Mission '{mission_id}' has not been submitted to Campaign Manager")
        self.campaign_manager.run_campaign(campaign_id)
        return self.reconcile_mission(mission_id)

    def approve_mission_job(self, mission_id: str, job_id: str) -> dict[str, Any]:
        """Approve a job waiting in WAITING_APPROVAL state via Campaign Manager."""
        self.campaign_manager.approve_job(job_id)
        return self.reconcile_mission(mission_id)

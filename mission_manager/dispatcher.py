from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Callable

from .adaptation import observations_for
from .models import JOB_STATES, MISSION_STATES, now, validate_plan
from .progress import human_status, update_progress
from .receipts import read_authoritative_receipt
from .router import RoutingError, route, sizing_flags
from .state import MissionStore
from .worker_registry import department, explicit_coding_fallback, registry
from supervisor.policy import classify_premature_stop


JOSIE_ROOT = Path(r"D:\Josie")
DEFAULT_MISSIONS = JOSIE_ROOT / "data" / "private" / "missions"
DEFAULT_RECEIPTS = JOSIE_ROOT / "data" / "private" / "supervisor-local-code"
DEFAULT_ORDERS = JOSIE_ROOT / "data" / "private" / "supervisor-work-orders"
MAX_MISSION_DISPATCH_ATTEMPTS = 2


class DispatchError(RuntimeError):
    pass


class MissionStateError(DispatchError):
    pass


class SupervisorFailure(DispatchError):
    pass


def _job(mission: dict, job_id: str) -> dict:
    try:
        return next(job for job in mission["jobs"] if job["job_id"] == job_id)
    except StopIteration as exc:
        raise KeyError(job_id) from exc


def _validate_state(mission: dict, expected_mission_id: str) -> None:
    if not isinstance(mission, dict) or mission.get("schema_version") != "1":
        raise MissionStateError("MALFORMED_MISSION_STATE: unsupported schema")
    if mission.get("mission_id") != expected_mission_id:
        raise MissionStateError("MALFORMED_MISSION_STATE: mission ID mismatch")
    if mission.get("status") not in MISSION_STATES:
        raise MissionStateError("MALFORMED_MISSION_STATE: invalid mission status")
    jobs = mission.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise MissionStateError("MALFORMED_MISSION_STATE: jobs are missing")
    ids = [job.get("job_id") for job in jobs if isinstance(job, dict)]
    if len(ids) != len(jobs) or any(not isinstance(item, str) for item in ids) or len(ids) != len(set(ids)):
        raise MissionStateError("MALFORMED_MISSION_STATE: invalid or duplicate job ID")
    by_id = {job["job_id"]: job for job in jobs}
    for job in jobs:
        if job.get("status") not in JOB_STATES:
            raise MissionStateError(f"MALFORMED_MISSION_STATE: invalid status for {job['job_id']}")
        dependencies = job.get("dependencies")
        if not isinstance(dependencies, list) or any(item not in by_id for item in dependencies):
            raise MissionStateError(f"MALFORMED_MISSION_STATE: invalid dependency for {job['job_id']}")
        attempts = job.get("attempts")
        dispatch_ids = job.get("dispatch_ids")
        if not isinstance(attempts, int) or attempts < 0 or not isinstance(dispatch_ids, list) or len(dispatch_ids) > attempts:
            raise MissionStateError(f"MALFORMED_MISSION_STATE: invalid attempts for {job['job_id']}")
        if job["status"] == "PASS":
            evidence = job.get("receipt_evidence") or {}
            if evidence.get("final_status") != "PASS" or evidence.get("receipt_id") not in mission.get("receipt_refs", []):
                raise MissionStateError(f"MALFORMED_MISSION_STATE: {job['job_id']} lacks authoritative PASS evidence")
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(job_id: str) -> None:
        if job_id in visiting:
            raise MissionStateError("DEPENDENCY_DEADLOCK: dependency cycle")
        if job_id in visited:
            return
        visiting.add(job_id)
        for dependency in by_id[job_id]["dependencies"]:
            visit(dependency)
        visiting.remove(job_id)
        visited.add(job_id)
    for job_id in ids:
        visit(job_id)


def _refresh(mission: dict) -> None:
    by_id = {job["job_id"]: job for job in mission["jobs"]}
    terminal_failure = False
    for job in mission["jobs"]:
        dependencies = [by_id[item]["status"] for item in job["dependencies"]]
        if job["status"] == "WAITING" and dependencies and any(item in {"FAIL", "BLOCKED", "SKIPPED"} for item in dependencies):
            job["status"] = "BLOCKED"
            job["result_reason"] = "BLOCKED_BY_DEPENDENCY"
        elif job["status"] == "WAITING" and all(item == "PASS" for item in dependencies):
            job["status"] = "READY"
        terminal_failure = terminal_failure or job["status"] == "FAIL"
    running = next((job["job_id"] for job in mission["jobs"] if job["status"] == "RUNNING"), None)
    ready = next((job["job_id"] for job in mission["jobs"] if job["status"] == "READY"), None)
    mission["current_job"] = running or ready
    update_progress(mission)
    required = [job for job in mission["jobs"] if job.get("required", True)]
    if required and all(
        job["status"] == "PASS"
        and (job.get("receipt_evidence") or {}).get("final_status") == "PASS"
        and (job.get("receipt_evidence") or {}).get("receipt_id") in mission.get("receipt_refs", [])
        for job in required
    ):
        mission["status"] = "COMPLETE"
        mission["current_job"] = None
    elif terminal_failure:
        mission["status"] = "FAILED"
    elif mission["status"] not in {"PLANNED", "CANCELLED"} and not running and not ready:
        mission["status"] = "BLOCKED"


class MissionManager:
    def __init__(self, mission_directory: Path = DEFAULT_MISSIONS, *, receipt_directory: Path = DEFAULT_RECEIPTS,
                 work_order_directory: Path = DEFAULT_ORDERS, supervisor_execute: Callable | None = None):
        self.store = MissionStore(mission_directory)
        self.receipt_directory = Path(receipt_directory).resolve()
        self.work_order_directory = Path(work_order_directory).resolve()
        self.receipt_directory.mkdir(parents=True, exist_ok=True)
        self.work_order_directory.mkdir(parents=True, exist_ok=True)
        self._execute = supervisor_execute

    def create(self, plan: dict) -> dict:
        mission = validate_plan(plan)
        _refresh(mission)
        self.store.create(mission)
        return mission

    def load(self, mission_id: str) -> dict:
        mission = self.store.load(mission_id)
        _validate_state(mission, mission_id)
        for job in mission["jobs"]:
            if job.get("receipt_ref"):
                expected = job["dispatch_ids"][-1] if job.get("dispatch_ids") else None
                receipt = read_authoritative_receipt(job["receipt_ref"], expected_job_id=expected)
                stored = job.get("receipt_evidence") or {}
                if stored.get("receipt_id") and stored["receipt_id"] != receipt["receipt_id"]:
                    raise MissionStateError(f"MALFORMED_MISSION_STATE: receipt mismatch for {job['job_id']}")
        _refresh(mission)
        return mission

    def status(self, mission_id: str) -> dict:
        mission = self.load(mission_id)
        return {"mission": mission, "human": human_status(mission), "workers": registry()}

    def sizing_check(self, mission_id: str, job_id: str) -> dict:
        job = _job(self.load(mission_id), job_id)
        flags = sizing_flags(job)
        return {"ok": not flags, "result": "OK" if not flags else "JOB_TOO_LARGE_FOR_WORKER", "flags": flags}

    def _work_order(self, mission: dict, job: dict, *, model: str | None = None,
                    max_attempts: int = 2) -> tuple[dict, Path]:
        attempt = job["attempts"] + 1
        work_id = f"mission-{mission['mission_id']}-{job['job_id']}-a{attempt}"
        harness = job.get("harness") or "coder"
        order = {
            "schema_version": "1", "job_id": work_id, "objective": job["objective"],
            "first_action": job.get("first_action") or "Inspect only the relevant existing source and tests, then make the bounded change.",
            "workspace": job["workspace"], "harness": harness,
            "primary_harness_executable": r"I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe",
            "fallback_harness_executable": r"I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe",
            "harness_executable": r"I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe" if harness == "opencode" else r"I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe",
            "harness_config": r"D:\Josie\config\opencode-local.json", "agent": "josie-coder",
            "agent_profile": r"D:\Josie\.opencode\agents\josie-coder.md",
            "model": model or department("coding")["model"],
            "context_limit": 8192, "max_tool_repetitions": 3,
            "side_effect_capabilities": [], "requires_modification": job.get("requires_modification", True),
            "allowed_changed_paths": job["allowed_changes"], "forbidden_paths": ["docs/identity", "docs/constitution", "JOSIE_CODEX_MASTER_CONTEXT.md"],
            "timeout_seconds": job["timeout"], "max_attempts": max_attempts,
            "acceptance": job["acceptance"], "prompt_profile": "josie-coder-v1",
            "receipt_destination": str(self.receipt_directory), "ollama_url": "http://127.0.0.1:11434",
        }
        from supervisor.work_order import WorkOrder
        WorkOrder.validate(order)
        target = self.work_order_directory / f"{work_id}.json"
        if target.exists():
            raise DispatchError(f"work order already exists: {target}")
        temporary = self.work_order_directory / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(order, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return order, target

    def dispatch_next(self, mission_id: str) -> dict:
        mission = self.load(mission_id)
        if mission["status"] in {"COMPLETE", "FAILED", "BLOCKED", "CANCELLED"}:
            raise DispatchError(f"mission cannot dispatch from {mission['status']}")
        if any(job["status"] == "RUNNING" for job in mission["jobs"]):
            raise DispatchError("a job is already running")
        job = next((item for item in mission["jobs"] if item["status"] == "READY"), None)
        if job is None:
            raise DispatchError("no job is ready")
        try:
            route(job)
        except RoutingError as exc:
            if str(exc).startswith("JOB_TOO_LARGE_FOR_WORKER"):
                mission["adaptation_observations"].append({"observed_at": now(), "job_id": job["job_id"],
                    "possible_adaptation": "DECOMPOSE_JOB", "strength": "PREFLIGHT_FLAG", "automatically_applied": False,
                    "basis": str(exc), "evidence": {"receipt_ids": [], "authorized_file_count": len(job["allowed_changes"])}})
                mission["updated_at"] = now()
                self.store.save(mission)
            raise DispatchError(str(exc)) from exc
        selected_model = job.get("pending_fallback_model")
        order, order_path = self._work_order(
            mission, job, model=selected_model,
            max_attempts=1 if selected_model else 2,
        )
        job["status"] = "RUNNING"
        job["attempts"] += 1
        job["dispatch_ids"].append(order["job_id"])
        job.setdefault("dispatch_models", []).append(order["model"])
        if selected_model:
            job["fallback_attempts"] = job.get("fallback_attempts", 0) + 1
            job.pop("pending_fallback_model", None)
        mission["status"] = "ACTIVE"
        mission["current_job"] = job["job_id"]
        mission["updated_at"] = now()
        self.store.save(mission)
        self.store.append_event(mission_id, {"event": "JOB_DISPATCHED", "at": mission["updated_at"], "job_id": job["job_id"], "work_order": str(order_path)})
        execute = self._execute
        if execute is None:
            from supervisor.run_job import execute
        try:
            receipt, receipt_path = execute(order_path)
            if receipt_path is None or not Path(receipt_path).is_file():
                raise SupervisorFailure("Supervisor produced no authoritative terminal receipt")
            return self.consume_receipt(mission_id, Path(receipt_path), job_id=job["job_id"])
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            failed = self.store.load(mission_id)
            failed_job = _job(failed, job["job_id"])
            failed_job["status"] = "BLOCKED"
            failed_job["result_reason"] = "SUPERVISOR_FAILURE"
            failed_job["management_error"] = type(exc).__name__
            failed["status"] = "BLOCKED"
            failed["current_job"] = None
            failed["updated_at"] = now()
            update_progress(failed)
            self.store.save(failed)
            self.store.append_event(mission_id, {"event": "SUPERVISOR_FAILURE", "at": failed["updated_at"],
                "job_id": job["job_id"], "error_type": type(exc).__name__})
            raise SupervisorFailure("SUPERVISOR_FAILURE") from exc

    def consume_receipt(self, mission_id: str, receipt_path: Path, *, job_id: str) -> dict:
        mission = self.load(mission_id)
        job = _job(mission, job_id)
        if not job["dispatch_ids"]:
            raise DispatchError("job has no Supervisor dispatch")
        evidence = read_authoritative_receipt(receipt_path, expected_job_id=job["dispatch_ids"][-1])
        if evidence["receipt_id"] in mission["receipt_refs"]:
            return mission
        status = evidence["final_status"]
        evidence["files_authorized"] = list(job["allowed_changes"])
        job["status"] = "PASS" if status == "PASS" else ("BLOCKED" if status == "BLOCKED" else "FAIL")
        job["receipt_ref"] = evidence["path"]
        job["result_reason"] = evidence["reason"]
        job["receipt_evidence"] = evidence
        mission["receipt_refs"].append(evidence["receipt_id"])
        mission["adaptation_observations"].extend(observations_for(job, evidence))
        mission["updated_at"] = now()
        _refresh(mission)
        self.store.save(mission)
        self.store.append_event(mission_id, {"event": "RECEIPT_CONSUMED", "at": mission["updated_at"],
            "job_id": job_id, "receipt_id": evidence["receipt_id"], "final_status": status, "reason": evidence["reason"]})
        return mission

    def continue_until_stop(self, mission_id: str, *, max_jobs: int = 12) -> dict:
        if not isinstance(max_jobs, int) or max_jobs <= 0:
            raise ValueError("max_jobs must be positive")
        dispatched: list[str] = []
        for _ in range(max_jobs):
            try:
                mission = self.load(mission_id)
            except MissionStateError as exc:
                if "DEPENDENCY_DEADLOCK" in str(exc):
                    raw_mission = self.store.load(mission_id)
                    return {"mission": raw_mission, "dispatched": dispatched, "stop_reason": "DEPENDENCY_DEADLOCK"}
                raise
            if mission["status"] in {"COMPLETE", "FAILED", "BLOCKED", "CANCELLED"}:
                return {"mission": mission, "dispatched": dispatched, "stop_reason": mission["status"]}
            ready = next((job for job in mission["jobs"] if job["status"] == "READY"), None)
            if ready is None:
                if any(job["status"] == "RUNNING" for job in mission["jobs"]):
                    return {"mission": mission, "dispatched": dispatched, "stop_reason": "RUNNING"}
                waiting = any(job["status"] == "WAITING" for job in mission["jobs"])
                reason = "DEPENDENCY_DEADLOCK" if waiting else "NO_READY_JOB"
                return {"mission": mission, "dispatched": dispatched, "stop_reason": reason}
            job_id = ready["job_id"]
            try:
                mission = self.dispatch_next(mission_id)
            except SupervisorFailure:
                return {"mission": self.load(mission_id), "dispatched": dispatched + [job_id],
                        "stop_reason": "SUPERVISOR_FAILURE"}
            dispatched.append(job_id)
            completed = _job(mission, job_id)
            if completed["status"] != "PASS":
                return {"mission": mission, "dispatched": dispatched,
                        "stop_reason": completed.get("result_reason") or completed["status"]}
        return {"mission": self.load(mission_id), "dispatched": dispatched, "stop_reason": "RESOURCE_BOUND"}

    def authorize_premature_stop_retry(self, mission_id: str, job_id: str, *,
                                       updated_objective: str | None = None,
                                       first_action: str | None = None) -> dict:
        """Apply one explicit mission-level retry transition backed by receipt evidence."""
        mission = self.load(mission_id)
        job = _job(mission, job_id)
        if job["status"] != "FAIL" or not job.get("receipt_ref"):
            raise DispatchError("job is not a failed receipt-backed attempt")
        if job["attempts"] >= MAX_MISSION_DISPATCH_ATTEMPTS:
            raise DispatchError("bounded mission retry limit reached")
        evidence = read_authoritative_receipt(job["receipt_ref"], expected_job_id=job["dispatch_ids"][-1])
        if not evidence.get("worker_launched") or not classify_premature_stop(
            requires_modification=job.get("requires_modification", True),
            exit_code=evidence.get("exit_code"), timed_out=evidence.get("timed_out", False),
            violations=evidence.get("scope_violations", []), changes=evidence.get("files_changed", []),
            acceptance=evidence.get("acceptance_results", []), tool_names=evidence.get("tool_activity", []),
            blocker_reported=evidence.get("blocker_reported", False),
            denied_actions=evidence.get("denied_capabilities", []),
        ):
            raise DispatchError("receipt does not evidence PREMATURE_STOP")

        history = job.setdefault("attempt_history", [])
        if not any(item.get("receipt_id") == evidence["receipt_id"] for item in history):
            history.append(evidence)
        if updated_objective is not None:
            if not isinstance(updated_objective, str) or not updated_objective.strip():
                raise ValueError("updated_objective must be nonempty")
            job["objective"] = updated_objective.strip()
        if first_action is not None:
            if not isinstance(first_action, str) or not first_action.strip():
                raise ValueError("first_action must be nonempty")
            job["first_action"] = first_action.strip()
        job["status"] = "READY"
        job["receipt_ref"] = None
        job.pop("receipt_evidence", None)
        job["result_reason"] = None
        for dependent in mission["jobs"]:
            if dependent.get("result_reason") == "BLOCKED_BY_DEPENDENCY":
                dependent["status"] = "WAITING"
                dependent["result_reason"] = None
        mission["status"] = "PLANNED"
        mission["current_job"] = job_id
        mission["updated_at"] = now()
        for category, basis in (
            ("PREMATURE_STOP", "normal worker exit with no tool action, no changes, and failed acceptance"),
            ("PROMPT_FIDELITY_REPAIR", "explicit job requirements restored before the authorized retry"),
        ):
            mission["adaptation_observations"].append({
                "observed_at": mission["updated_at"], "job_id": job_id,
                "possible_adaptation": category, "strength": "EVIDENCED",
                "automatically_applied": False, "basis": basis,
                "evidence": {"receipt_ids": [evidence["receipt_id"]],
                             "elapsed_seconds": evidence.get("elapsed_seconds"),
                             "failure_reason": evidence.get("reason"),
                             "authorized_file_count": len(job.get("allowed_changes", [])),
                             "changed_file_count": len(evidence.get("files_changed", []))},
            })
        _refresh(mission)
        self.store.save(mission)
        self.store.append_event(mission_id, {"event": "PREMATURE_STOP_RETRY_AUTHORIZED",
            "at": mission["updated_at"], "job_id": job_id, "receipt_id": evidence["receipt_id"],
            "next_attempt": job["attempts"] + 1})
        return self.load(mission_id)

    def authorize_fallback_retry(self, mission_id: str, fallback_worker: str) -> dict:
        """Authorize one explicit receipt-backed retry on a named fallback model."""
        try:
            selected_model = explicit_coding_fallback(fallback_worker)
        except KeyError as exc:
            raise DispatchError(str(exc)) from exc
        mission = self.load(mission_id)
        from supervisor.policy import is_hard_blocker
        candidates = [job for job in mission["jobs"] if job.get("department") == "coding"
                      and job.get("status") in {"FAIL", "BLOCKED"}
                      and job.get("receipt_ref")]
        if len(candidates) != 1:
            raise DispatchError("mission must have exactly one failed receipt-backed coding job")
        job = candidates[0]
        if job["status"] == "BLOCKED" and is_hard_blocker(job.get("result_reason", "")):
            raise DispatchError(f"hard blocker cannot be retried via fallback: {job.get('result_reason')}")
        if job.get("fallback_attempts", 0) >= 1 or selected_model in job.get("dispatch_models", []):
            raise DispatchError("bounded fallback retry limit reached")
        evidence = read_authoritative_receipt(
            job["receipt_ref"], expected_job_id=job["dispatch_ids"][-1])
        history = job.setdefault("attempt_history", [])
        if not any(item.get("receipt_id") == evidence["receipt_id"] for item in history):
            history.append(evidence)
        job["status"] = "READY"
        job["receipt_ref"] = None
        job.pop("receipt_evidence", None)
        job["result_reason"] = None
        job["pending_fallback_model"] = selected_model
        for dependent in mission["jobs"]:
            if dependent.get("result_reason") == "BLOCKED_BY_DEPENDENCY":
                dependent["status"] = "WAITING"
                dependent["result_reason"] = None
        mission["status"] = "PLANNED"
        mission["current_job"] = job["job_id"]
        mission["updated_at"] = now()
        _refresh(mission)
        self.store.save(mission)
        self.store.append_event(mission_id, {
            "event": "FALLBACK_RETRY_AUTHORIZED", "at": mission["updated_at"],
            "job_id": job["job_id"], "previous_receipt_id": evidence["receipt_id"],
            "fallback_model": selected_model, "next_attempt": job["attempts"] + 1,
        })
        return self.load(mission_id)

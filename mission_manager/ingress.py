from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from .dispatcher import DispatchError, MissionManager, MissionStateError, SupervisorFailure
from .models import JOB_STATES, MISSION_STATES, PlanValidationError
from .progress import SYMBOLS
from .receipts import read_authoritative_receipt


MISSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}")


def _validated_id(value: object) -> str:
    if not isinstance(value, str) or MISSION_ID.fullmatch(value) is None:
        raise ValueError("mission_id is invalid")
    return value


def _checklist(mission: dict) -> str:
    lines = []
    for job in mission["jobs"]:
        if job.get("result_reason") == "SUPERSEDED_BY_DECOMPOSITION":
            symbol = "[SUPERSEDED]"
        else:
            symbol = SYMBOLS.get(job["status"], "[UNKNOWN]")
        lines.append(f"{symbol} {job['title']}")
    return "\n".join(lines)


def _public(mission: dict, *, dispatched: list[str], stop_reason: str) -> dict:
    by_id = {job["job_id"]: job for job in mission["jobs"]}
    if any(job_id not in by_id or not by_id[job_id].get("dispatch_ids") for job_id in dispatched):
        raise ValueError("result consistency gate rejected unproven dispatch")
    if mission.get("status") not in MISSION_STATES or mission.get("status") in {"SUCCESS", "VERIFIED_COMPLETE"}:
        raise ValueError(f"result consistency gate rejected invalid mission status: {mission.get('status')}")
    for job in mission.get("jobs", []):
        if job.get("status") not in JOB_STATES or job.get("status") in {"SUCCESS", "VERIFIED_COMPLETE"}:
            raise ValueError(f"result consistency gate rejected invalid job status: {job.get('status')}")
        if job.get("status") == "PASS":
            receipt_ref = job.get("receipt_ref")
            if not receipt_ref:
                raise ValueError(f"result consistency gate rejected PASS job without receipt: {job.get('job_id')}")
            receipt_path = Path(receipt_ref)
            if not receipt_path.is_file():
                raise ValueError(f"result consistency gate rejected missing receipt file: {receipt_ref}")
            try:
                receipt_data = read_authoritative_receipt(receipt_path)
            except Exception as exc:
                raise ValueError(f"result consistency gate rejected unreadable receipt: {exc}")
            if receipt_data.get("final_status") != "PASS":
                raise ValueError(f"result consistency gate rejected non-PASS receipt: {receipt_data.get('final_status')}")
            valid_jobs = set(job.get("dispatch_ids") or []) | {job.get("job_id")}
            receipt_job_id = receipt_data.get("job_id") or receipt_data.get("work_order_id")
            if receipt_job_id not in valid_jobs:
                raise ValueError(f"result consistency gate rejected receipt job mismatch: expected {job.get('job_id')}, got {receipt_job_id}")
            acceptance_results = receipt_data.get("acceptance_results") or []
            if not acceptance_results or not all(item.get("passed") is True for item in acceptance_results):
                raise ValueError(f"result consistency gate rejected unpassed machine acceptance in receipt for {job.get('job_id')}")
            workspace = Path(job.get("workspace", "."))
            for check in job.get("acceptance", []):
                if isinstance(check, dict) and check.get("type") in ("file_exists", "file_exact"):
                    check_path = check.get("path")
                    if check_path:
                        art_path = (workspace / check_path).resolve()
                        if not art_path.is_file():
                            raise ValueError(f"result consistency gate rejected missing deliverable artifact: {check_path}")

    required = [job for job in mission["jobs"] if job.get("required", True)]
    if mission["status"] == "COMPLETE" and any(
        job["status"] != "PASS" or (job.get("receipt_evidence") or {}).get("final_status") != "PASS"
        for job in required
    ):
        raise ValueError("result consistency gate rejected unproven completion")
    not_run = [job["job_id"] for job in mission["jobs"] if job.get("attempts", 0) == 0 and job.get("required", True)]
    receipt_paths = [job.get("receipt_ref") for job in mission["jobs"] if job.get("receipt_ref")]
    progress = mission["progress"]
    message = "\n".join((
        "JOSIE MISSION MANAGER — ACTUAL RESULT",
        f"Mission: {mission['mission_id']} ({mission['title']})",
        f"Mission status: {mission['status']}",
        f"Stop reason: {stop_reason}",
        f"Progress: {progress['completed']}/{progress['total']} complete",
        _checklist(mission),
        f"Jobs dispatched this request: {', '.join(dispatched) or 'none'}",
        f"Jobs NOT_RUN: {', '.join(not_run) or 'none'}",
        f"Latest authoritative receipt: {receipt_paths[-1] if receipt_paths else 'none'}",
        "Authority: Supervisor receipts only; worker narrative ignored.",
    ))
    return {
        "schema_version": 1, "mission_id": mission["mission_id"], "mission_status": mission["status"],
        "stop_reason": stop_reason, "progress": progress, "checklist": _checklist(mission),
        "jobs_dispatched": dispatched, "jobs_not_run": not_run,
        "latest_authoritative_receipt": receipt_paths[-1] if receipt_paths else None,
        "supervisor_invoked": bool(dispatched), "direct_worker_bypass": False,
        "worker_narrative_authority": False, "assistant_message": message,
    }


def submit_mission(plan: dict | Path | str, *, project_root: Path) -> dict:
    try:
        if isinstance(plan, (str, Path)):
            plan_data = json.loads(Path(plan).read_text(encoding="utf-8"))
        elif isinstance(plan, dict):
            plan_data = plan
        else:
            raise PlanValidationError("plan must be a dictionary or path to JSON")
    except Exception as exc:
        return {
            "schema_version": 1,
            "status": "rejected",
            "reason": "INVALID_PLAN",
            "assistant_message": f"JOSIE MISSION MANAGER — REQUEST REJECTED\nReason: {exc}",
        }

    mission_id = plan_data.get("mission_id")
    manager = MissionManager(
        Path(project_root) / "data" / "private" / "missions",
        receipt_directory=Path(project_root) / "data" / "private" / "supervisor-local-code",
        work_order_directory=Path(project_root) / "data" / "private" / "supervisor-work-orders",
    )
    if isinstance(mission_id, str) and manager.store.path(mission_id).exists():
        mission = manager.load(mission_id)
        return _public(mission, dispatched=[], stop_reason="ALREADY_EXISTS")

    try:
        mission = manager.create(plan_data)
        return _public(mission, dispatched=[], stop_reason="SUBMITTED")
    except (PlanValidationError, ValueError) as exc:
        return {
            "schema_version": 1,
            "status": "rejected",
            "reason": "INVALID_PLAN",
            "assistant_message": f"JOSIE MISSION MANAGER — REQUEST REJECTED\nReason: {exc}",
        }


def continue_mission(mission_id: object, *, project_root: Path, request_id: object | None = None,
                     fallback_worker: object | None = None,
                     supervisor_execute: Callable | None = None) -> dict:
    del request_id
    try:
        value = _validated_id(mission_id)
    except ValueError:
        return {"schema_version": 1, "status": "rejected", "reason": "INVALID_MISSION_ID",
                "assistant_message": "JOSIE MISSION MANAGER — REQUEST REJECTED\nReason: INVALID_MISSION_ID"}
    manager = MissionManager(Path(project_root) / "data" / "private" / "missions",
                             receipt_directory=Path(project_root) / "data" / "private" / "supervisor-local-code",
                             work_order_directory=Path(project_root) / "data" / "private" / "supervisor-work-orders",
                             supervisor_execute=supervisor_execute)
    try:
        if fallback_worker is not None:
            if not isinstance(fallback_worker, str):
                raise DispatchError("fallback worker is invalid")
            manager.authorize_fallback_retry(value, fallback_worker)
        outcome = manager.continue_until_stop(value)
        return _public(outcome["mission"], dispatched=outcome["dispatched"], stop_reason=outcome["stop_reason"])
    except FileNotFoundError:
        return {"schema_version": 1, "mission_id": value, "status": "not_found", "reason": "NEEDS_MISSION",
                "assistant_message": f"JOSIE MISSION MANAGER — NEEDS_MISSION\nMission not found: {value}"}
    except MissionStateError as exc:
        return {"schema_version": 1, "mission_id": value, "status": "blocked", "reason": "MALFORMED_MISSION_STATE",
                "assistant_message": f"JOSIE MISSION MANAGER — ACTUAL RESULT\nMission: {value}\nMission status: BLOCKED\nStop reason: {str(exc).split(':', 1)[0]}\nNo job was dispatched."}
    except DispatchError as exc:
        return {"schema_version": 1, "mission_id": value, "status": "rejected",
                "reason": "FALLBACK_NOT_AUTHORIZED",
                "assistant_message": f"JOSIE MISSION MANAGER — REQUEST REJECTED\nReason: {exc}\nNo job was dispatched."}
    except ValueError as exc:
        return {"schema_version": 1, "mission_id": value, "status": "unverified", "reason": "EVIDENCE_NOT_FOUND",
                "assistant_message": "MISSION RESULT NOT VERIFIED\nReason: authoritative persisted mission evidence was not found."}


def mission_status(mission_id: object, *, project_root: Path) -> dict:
    try:
        value = _validated_id(mission_id)
    except ValueError:
        return {"schema_version": 1, "status": "rejected", "reason": "INVALID_MISSION_ID",
                "assistant_message": "JOSIE MISSION MANAGER — REQUEST REJECTED\nReason: INVALID_MISSION_ID"}
    manager = MissionManager(Path(project_root) / "data" / "private" / "missions",
                             receipt_directory=Path(project_root) / "data" / "private" / "supervisor-local-code",
                             work_order_directory=Path(project_root) / "data" / "private" / "supervisor-work-orders")
    try:
        mission = manager.load(value)
        return _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
    except FileNotFoundError:
        return {"schema_version": 1, "mission_id": value, "status": "not_found", "reason": "NEEDS_MISSION",
                "assistant_message": f"JOSIE MISSION MANAGER — NEEDS_MISSION\nMission not found: {value}"}
    except (MissionStateError, ValueError) as exc:
        return {"schema_version": 1, "mission_id": value, "status": "unverified", "reason": "EVIDENCE_NOT_FOUND",
                "assistant_message": "MISSION RESULT NOT VERIFIED\nReason: authoritative persisted mission evidence was not found."}

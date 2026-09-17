from __future__ import annotations

import datetime as dt
import re
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any


MISSION_STATES = {"PLANNED", "SUBMITTED", "ACTIVE", "RUNNING", "WAITING_APPROVAL", "BLOCKED", "FAILED", "COMPLETE", "COMPLETED", "CANCELLED"}
JOB_STATES = {"WAITING", "READY", "RUNNING", "PASS", "FAIL", "BLOCKED", "SKIPPED"}
DEPARTMENTS = {"coding", "research", "image", "marketing", "social"}
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,63}")


class PlanValidationError(ValueError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(f"{name} must be a nonempty string")
    return value.strip()


def _relative(value: Any) -> str:
    value = _text(value, "allowed change").replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise PlanValidationError(f"unsafe allowed change: {value}")
    return path.as_posix().lstrip("./")


def validate_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise PlanValidationError("mission plan must be an object")
    mission_id = _text(plan.get("mission_id"), "mission_id")
    if not ID.fullmatch(mission_id):
        raise PlanValidationError("mission_id contains unsupported characters")
    title = _text(plan.get("title"), "title")
    objective = _text(plan.get("objective"), "objective")
    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise PlanValidationError("jobs must be a nonempty list")

    jobs: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            raise PlanValidationError(f"jobs[{index}] must be an object")
        job_id = _text(raw.get("job_id"), f"jobs[{index}].job_id")
        if not ID.fullmatch(job_id) or job_id in ids:
            raise PlanValidationError(f"invalid or duplicate job_id: {job_id}")
        ids.add(job_id)
        department = _text(raw.get("department"), f"jobs[{index}].department").lower()
        if department not in DEPARTMENTS:
            raise PlanValidationError(f"unknown department: {department}")
        workspace_input = Path(_text(raw.get("workspace"), f"jobs[{index}].workspace"))
        if not workspace_input.is_absolute():
            raise PlanValidationError(f"workspace must be an existing absolute directory: {workspace_input}")
        workspace = workspace_input.resolve()
        if not workspace.is_dir():
            raise PlanValidationError(f"workspace must be an existing absolute directory: {workspace}")
        allowed = raw.get("allowed_changes")
        if not isinstance(allowed, list) or not allowed:
            raise PlanValidationError(f"jobs[{index}].allowed_changes must be nonempty")
        acceptance = raw.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            raise PlanValidationError(f"jobs[{index}].acceptance must be nonempty")
        timeout = raw.get("timeout", 120)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise PlanValidationError(f"jobs[{index}].timeout must be positive")
        dependencies = raw.get("dependencies", [])
        if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
            raise PlanValidationError(f"jobs[{index}].dependencies must be a string list")
        responsibilities = raw.get("independent_responsibilities", [])
        if not isinstance(responsibilities, list) or any(not isinstance(item, str) for item in responsibilities):
            raise PlanValidationError(f"jobs[{index}].independent_responsibilities must be a string list")
        jobs.append({
            "job_id": job_id,
            "title": _text(raw.get("title"), f"jobs[{index}].title"),
            "department": department,
            "objective": _text(raw.get("objective"), f"jobs[{index}].objective"),
            "first_action": (_text(raw.get("first_action"), f"jobs[{index}].first_action")
                             if raw.get("first_action") is not None else None),
            "dependencies": list(dict.fromkeys(dependencies)),
            "status": "WAITING",
            "workspace": str(workspace),
            "allowed_changes": [_relative(item) for item in allowed],
            "acceptance": deepcopy(acceptance),
            "timeout": timeout,
            "attempts": 0,
            "receipt_ref": None,
            "result_reason": None,
            "required": bool(raw.get("required", True)),
            "requires_modification": bool(raw.get("requires_modification", True)),
            "independent_responsibilities": responsibilities,
            "dispatch_ids": [],
        })

    by_id = {job["job_id"]: job for job in jobs}
    for job in jobs:
        missing = sorted(set(job["dependencies"]) - ids)
        if missing:
            raise PlanValidationError(f"{job['job_id']} has unknown dependencies: {', '.join(missing)}")
        if job["job_id"] in job["dependencies"]:
            raise PlanValidationError(f"{job['job_id']} cannot depend on itself")

    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(job_id: str) -> None:
        if job_id in visiting:
            raise PlanValidationError("dependency graph contains a cycle")
        if job_id in visited:
            return
        visiting.add(job_id)
        for dependency in by_id[job_id]["dependencies"]:
            visit(dependency)
        visiting.remove(job_id)
        visited.add(job_id)
    for job_id in ids:
        visit(job_id)

    for job in jobs:
        if not job["dependencies"]:
            job["status"] = "READY"
    created = now()
    return {
        "schema_version": "1",
        "mission_id": mission_id,
        "title": title,
        "objective": objective,
        "created_at": created,
        "updated_at": created,
        "status": "PLANNED",
        "jobs": jobs,
        "dependency_graph": {job["job_id"]: job["dependencies"] for job in jobs},
        "current_job": None,
        "receipt_refs": [],
        "progress": {"completed": 0, "total": sum(job["required"] for job in jobs), "percent": 0},
        "adaptation_observations": [],
    }

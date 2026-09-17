from __future__ import annotations

from typing import Any

from .constants import JobState, VALID_JOB_STATES
from .errors import CycleDetectedError, ValidationError

REQUIRED_JOB_FIELDS = {"job_id", "name", "work_order", "dependencies", "max_attempts", "retry_safe"}
REQUIRED_WORK_ORDER_FIELDS = {
    "schema_version", "job_id", "objective", "workspace", "harness",
    "model", "allowed_changed_paths", "timeout_seconds", "max_attempts",
    "acceptance", "prompt_profile", "receipt_destination",
}


def detect_cycles(jobs: list[dict[str, Any]]) -> None:
    """Detect cycles in job dependencies using depth-first search.
    
    Raises CycleDetectedError if a cycle is found.
    """
    adj: dict[str, list[str]] = {job["job_id"]: list(job.get("dependencies", [])) for job in jobs}
    visited: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=visited
    path: list[str] = []

    def dfs(node: str) -> None:
        visited[node] = 1
        path.append(node)
        for neighbor in adj.get(node, []):
            if neighbor not in adj:
                continue
            state = visited.get(neighbor, 0)
            if state == 1:
                # Cycle detected
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                raise CycleDetectedError(f"Dependency cycle detected: {' -> '.join(cycle)}")
            elif state == 0:
                dfs(neighbor)
        path.pop()
        visited[node] = 2

    for job_id in adj:
        if visited.get(job_id, 0) == 0:
            dfs(job_id)


def validate_work_order_payload(work_order: Any, job_id: str) -> None:
    """Validate that work order payload conforms to supervisor expectations."""
    if not isinstance(work_order, dict):
        raise ValidationError(f"Job '{job_id}' work_order must be a JSON object")
    missing = REQUIRED_WORK_ORDER_FIELDS - work_order.keys()
    if missing:
        raise ValidationError(f"Job '{job_id}' work_order missing required fields: {sorted(list(missing))}")
    if not isinstance(work_order.get("schema_version"), str) or not work_order["schema_version"].strip():
        raise ValidationError(f"Job '{job_id}' work_order schema_version must be a non-empty string")
    if not isinstance(work_order.get("allowed_changed_paths"), list) or not work_order["allowed_changed_paths"]:
        raise ValidationError(f"Job '{job_id}' work_order allowed_changed_paths must be a non-empty list")
    if not isinstance(work_order.get("acceptance"), list) or not work_order["acceptance"]:
        raise ValidationError(f"Job '{job_id}' work_order acceptance must be a non-empty list")


def validate_campaign_spec(spec: Any) -> dict[str, Any]:
    """Validate full campaign specification before database insertion.
    
    Raises ValidationError or CycleDetectedError on any malformed input.
    """
    if not isinstance(spec, dict):
        raise ValidationError("Campaign specification must be a JSON object")
    name = spec.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Campaign 'name' must be a non-empty string")
    jobs = spec.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValidationError("Campaign 'jobs' must be a non-empty list")

    seen_ids: set[str] = set()
    for idx, job in enumerate(jobs):
        if not isinstance(job, dict):
            raise ValidationError(f"Job at index {idx} must be a JSON object")
        missing = REQUIRED_JOB_FIELDS - job.keys()
        if missing:
            raise ValidationError(f"Job at index {idx} missing required fields: {sorted(list(missing))}")
        
        job_id = job["job_id"]
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValidationError(f"Job at index {idx}: 'job_id' must be a non-empty string")
        if job_id in seen_ids:
            raise ValidationError(f"Duplicate job_id '{job_id}' in campaign")
        seen_ids.add(job_id)

        job_name = job["name"]
        if not isinstance(job_name, str) or not job_name.strip():
            raise ValidationError(f"Job '{job_id}': 'name' must be a non-empty string")

        max_attempts = job["max_attempts"]
        if not isinstance(max_attempts, int) or max_attempts <= 0:
            raise ValidationError(f"Job '{job_id}': 'max_attempts' must be a positive integer")

        retry_safe = job["retry_safe"]
        if not isinstance(retry_safe, bool):
            raise ValidationError(f"Job '{job_id}': 'retry_safe' must be a boolean")

        dependencies = job["dependencies"]
        if not isinstance(dependencies, list) or not all(isinstance(d, str) for d in dependencies):
            raise ValidationError(f"Job '{job_id}': 'dependencies' must be a list of strings")

        initial_state = job.get("initial_state", JobState.QUEUED)
        if initial_state not in VALID_JOB_STATES:
            raise ValidationError(f"Job '{job_id}': invalid initial_state '{initial_state}'")

        validate_work_order_payload(job["work_order"], job_id)

    # Check all dependency references are known jobs
    for job in jobs:
        for dep in job["dependencies"]:
            if dep not in seen_ids:
                raise ValidationError(f"Job '{job['job_id']}' depends on unknown job '{dep}'")
            if dep == job["job_id"]:
                raise CycleDetectedError(f"Job '{job['job_id']}' cannot depend on itself")

    # Check for cycles
    detect_cycles(jobs)

    return spec

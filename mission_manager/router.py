from __future__ import annotations

from .worker_registry import department


class RoutingError(RuntimeError):
    pass


def sizing_flags(job: dict) -> list[str]:
    if job["department"] != "coding":
        return []
    flags = []
    if len(job.get("allowed_changes", [])) > 3:
        flags.append("MORE_THAN_3_EDITABLE_FILES")
    if len(job.get("independent_responsibilities", [])) > 1:
        flags.append("MULTIPLE_INDEPENDENT_RESPONSIBILITIES")
    words = job.get("objective", "").lower()
    categories = sum(term in words for term in ("architecture", "implement", "documentation", "integrat"))
    if categories >= 4:
        flags.append("ARCHITECTURE_IMPLEMENTATION_DOCS_INTEGRATION")
    return flags


def route(job: dict) -> dict:
    target = department(job["department"])
    if target["status"] != "AVAILABLE":
        raise RoutingError(f"DEPARTMENT_UNAVAILABLE: {job['department']}")
    flags = sizing_flags(job)
    if flags:
        raise RoutingError("JOB_TOO_LARGE_FOR_WORKER: " + ", ".join(flags))
    return target

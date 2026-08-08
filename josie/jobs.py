"""Bounded local job orchestration with an explicit handler registry."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from .config import Config
from .diagnostics import health_check, memory_export_snapshot, restore_drill_snapshot
from .storage import LocalStore


Handler = Callable[[Config, Path, dict[str, object]], dict[str, object]]


def _health(config: Config, root: Path, payload: dict[str, object]) -> dict[str, object]:
    if payload:
        raise ValueError("health_check accepts no payload")
    return health_check(config=config, project_root=root)


def _restore_drill(config: Config, root: Path, payload: dict[str, object]) -> dict[str, object]:
    if payload:
        raise ValueError("restore_drill accepts no payload")
    return restore_drill_snapshot(config=config, project_root=root)


def _memory_export(config: Config, root: Path, payload: dict[str, object]) -> dict[str, object]:
    if payload:
        raise ValueError("memory_export accepts no payload")
    return memory_export_snapshot(config=config, project_root=root)


_HANDLERS: dict[str, Handler] = {
    "health_check": _health,
    "memory_export": _memory_export,
    "restore_drill": _restore_drill,
}


def available_job_handlers() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


class JobRunner:
    def __init__(self, *, config: Config, project_root: Path, store: LocalStore) -> None:
        self.config = config
        self.project_root = project_root
        self.store = store

    def queue(self, handler: str, payload: dict[str, object] | None = None, max_attempts: int = 2) -> int:
        if handler not in _HANDLERS:
            raise ValueError(f"Job handler is not allowed: {handler}")
        safe_payload = payload or {}
        if not isinstance(safe_payload, dict):
            raise ValueError("Job payload must be an object")
        rendered = json.dumps(safe_payload, sort_keys=True)
        if len(rendered) > 4096:
            raise ValueError("Job payload is too large")
        return self.store.enqueue_job(handler, rendered, max_attempts)

    def run_one(self) -> dict[str, object]:
        job = self.store.claim_next_job()
        if job is None:
            return {"status": "idle", "executed": False}
        job_id = int(job["id"])
        try:
            handler = _HANDLERS[str(job["handler"])]
            payload = json.loads(str(job["payload_json"]))
            if not isinstance(payload, dict):
                raise ValueError("Stored payload is not an object")
            result = handler(self.config, self.project_root, payload)
            self.store.finish_job(job_id, json.dumps(result, sort_keys=True, default=str))
            return {"status": "succeeded", "job_id": job_id, "handler": job["handler"]}
        except Exception as exc:
            next_status = self.store.fail_job(job_id, f"{type(exc).__name__}: {exc}")
            return {
                "status": next_status, "job_id": job_id, "handler": job["handler"],
                "error_type": type(exc).__name__, "generated_code_executed": False,
            }

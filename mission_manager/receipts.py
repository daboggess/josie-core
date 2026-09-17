from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReceiptError(ValueError):
    pass


def read_authoritative_receipt(path: Path, *, expected_job_id: str | None = None) -> dict[str, Any]:
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReceiptError("receipt must be an object")
    if not isinstance(data.get("supervisor_version"), str) or not data.get("supervisor_version"):
        raise ReceiptError("receipt is not identified as a Supervisor receipt")
    status = data.get("final_status") or data.get("status")
    reason = data.get("reason") or status
    job_id = data.get("job_id") or data.get("work_order_id")
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        raise ReceiptError("receipt has no authoritative terminal status")
    if expected_job_id is not None and job_id != expected_job_id:
        raise ReceiptError(f"receipt job mismatch: expected {expected_job_id}, got {job_id}")
    receipt_id = data.get("receipt_id") or path.stem
    acceptance = data.get("acceptance_results") or data.get("acceptance") or []
    changed = data.get("worker_changed_paths") or data.get("changed_files") or []
    return {
        "receipt_id": receipt_id,
        "path": str(path),
        "job_id": job_id,
        "final_status": status,
        "reason": reason,
        "worker": data.get("agent") or data.get("worker") or "Coder Worker v1",
        "model": data.get("requested_model") or data.get("model"),
        "elapsed_seconds": data.get("elapsed_seconds"),
        "attempt": data.get("attempt", 1),
        "files_authorized": data.get("allowed_changed_paths") or [],
        "files_changed": changed,
        "acceptance_results": acceptance,
        "timed_out": bool(data.get("timed_out", reason == "FAIL_TIMEOUT")),
        "exit_code": data.get("exit_code"),
        "worker_launched": bool(data.get("worker_launched", True)),
        "blocker_reported": bool(data.get("blocker_reported", False)),
        "scope_violations": data.get("scope_violations") or [],
        "denied_capabilities": (data.get("side_effect_policy") or {}).get("denied_actions", []),
        "tool_activity": data.get("tool_activity") or [],
    }

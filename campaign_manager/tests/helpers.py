from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any


def sample_work_order(
    job_id: str,
    workspace: Path | str,
    receipt_dest: Path | str,
    harness: str = "mock",
    objective: str = "allowed",
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "job_id": job_id,
        "objective": objective,
        "workspace": str(workspace),
        "harness": harness,
        "harness_executable": sys.executable if harness == "mock" else "",
        "model": "mock/exact" if harness == "mock" else "qwen3:14b",
        "allowed_changed_paths": ["allowed.txt"],
        "timeout_seconds": timeout_seconds,
        "max_attempts": 1,
        "acceptance": [{"type": "file_exists", "path": "allowed.txt"}],
        "prompt_profile": "test",
        "receipt_destination": str(receipt_dest),
    }


def sample_campaign_spec(
    workspace: Path | str,
    receipt_dest: Path | str,
    name: str = "Test Campaign",
    job_count: int = 3,
) -> dict[str, Any]:
    cid = f"camp-{uuid.uuid4().hex[:8]}"
    jobs = []
    for i in range(1, job_count + 1):
        jid = f"job-{i}"
        jobs.append({
            "job_id": jid,
            "name": f"Job {i}",
            "work_order": sample_work_order(jid, workspace, receipt_dest),
            "dependencies": [f"job-{i-1}"] if i > 1 else [],
            "max_attempts": 2,
            "retry_safe": True,
        })
    return {
        "campaign_id": cid,
        "name": name,
        "jobs": jobs,
    }

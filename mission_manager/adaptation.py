from __future__ import annotations

from typing import Any

from .models import now


def observations_for(job: dict, receipt: dict) -> list[dict[str, Any]]:
    categories: list[tuple[str, str]] = []
    reason = receipt["reason"]
    oversized = len(job.get("allowed_changes", [])) > 3 or len(job.get("independent_responsibilities", [])) > 1
    if reason == "FAIL_TIMEOUT" and oversized:
        categories.append(("DECOMPOSE_JOB", "Supervisor receipt records a timeout"))
    elif reason == "FAIL_TIMEOUT":
        categories.append(("REVIEW_REQUIRED", "small bounded job timed out without evidence that decomposition is appropriate"))
    if reason == "FAIL_SCOPE":
        categories.append(("REDUCE_ALLOWED_SCOPE", "Supervisor receipt records a scope failure"))
    if not receipt.get("files_changed") and receipt["final_status"] != "PASS":
        categories.append(("INCREASE_CONTEXT_PREPARATION", "failed attempt changed no files"))
    if len(job.get("allowed_changes", [])) > 3:
        categories.append(("DECOMPOSE_JOB", "job authorized more than three editable paths"))
    seen = set()
    output = []
    for category, basis in categories:
        if category in seen:
            continue
        seen.add(category)
        output.append({
            "observed_at": now(), "job_id": job["job_id"], "possible_adaptation": category,
            "strength": "OBSERVATION", "automatically_applied": False, "basis": basis,
            "evidence": {"receipt_ids": [receipt["receipt_id"]], "elapsed_seconds": receipt.get("elapsed_seconds"),
                         "failure_reason": reason, "authorized_file_count": len(job.get("allowed_changes", [])),
                         "changed_file_count": len(receipt.get("files_changed", []))},
        })
    return output

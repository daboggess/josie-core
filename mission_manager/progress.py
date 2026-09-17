from __future__ import annotations


SYMBOLS = {"PASS": "[PASS]", "RUNNING": "[RUN]", "READY": "[READY]", "WAITING": "[WAIT]", "FAIL": "[FAIL]", "BLOCKED": "[BLOCKED]", "SKIPPED": "[SKIP]"}


def update_progress(mission: dict) -> None:
    required = [job for job in mission["jobs"] if job.get("required", True)]
    completed = sum(
        job["status"] == "PASS"
        and (job.get("receipt_evidence") or {}).get("final_status") == "PASS"
        and (job.get("receipt_evidence") or {}).get("receipt_id") in mission.get("receipt_refs", [])
        for job in required
    )
    total = len(required)
    mission["progress"] = {"completed": completed, "total": total, "percent": round(100 * completed / total) if total else 100}


def human_status(mission: dict) -> str:
    progress = mission["progress"]
    lines = [f"{mission['title']} - {progress['completed']}/{progress['total']} complete"]
    for job in mission["jobs"]:
        lines.append(f"{SYMBOLS.get(job['status'], '?')} {job['title']}")
    return "\n".join(lines)

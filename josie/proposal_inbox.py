"""Ingest bounded Open WebUI proposal files without executing them."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .config import Config
from .policy import permission_for
from .storage import LocalStore


ALLOWED_KINDS = {"health_check", "memory_export", "restore_drill"}
EXPECTED_FIELDS = {
    "schema_version", "external_id", "created_at", "source", "kind", "summary",
    "status", "actions_queued", "actions_executed", "model_parameters_accepted",
    "cloud_activity",
}
MAX_FILE_BYTES = 8_192
MAX_FILES_PER_RUN = 100


def _validated(path: Path) -> dict[str, object]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("proposal file exceeds 8192 bytes")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != EXPECTED_FIELDS:
        raise ValueError("proposal fields are invalid")
    try:
        UUID(str(raw["external_id"]))
        datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("proposal identity or timestamp is invalid") from exc
    if path.stem != raw["external_id"]:
        raise ValueError("proposal filename does not match its identity")
    if raw["schema_version"] != 1 or raw["source"] != "openwebui":
        raise ValueError("proposal source or schema is invalid")
    if raw["kind"] not in ALLOWED_KINDS:
        raise ValueError("proposal kind is not allowlisted")
    summary = raw["summary"]
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 1_000:
        raise ValueError("proposal summary is invalid")
    fail_closed_values = {
        "status": "review_required",
        "actions_queued": 0,
        "actions_executed": 0,
        "model_parameters_accepted": False,
        "cloud_activity": False,
    }
    if any(raw[key] != expected for key, expected in fail_closed_values.items()):
        raise ValueError("proposal claims authority or external activity")
    return raw


def ingest_proposal_inbox(
    *, config: Config, project_root: Path, store: LocalStore
) -> dict[str, object]:
    permission = permission_for("record_local_fact", project_root)
    if permission["decision"] != "autonomous":
        raise RuntimeError("Proposal ingestion is not permitted by local policy")
    if not config.external_storage:
        return {"status": "waiting", "reason": "External storage is not configured"}

    root = config.external_storage / "proposals"
    inbox = root / "inbox"
    processed = root / "processed"
    rejected = root / "rejected"
    for directory in (inbox, processed, rejected):
        directory.mkdir(parents=True, exist_ok=True)

    result: dict[str, object] = {
        "status": "ok",
        "inspected": 0,
        "ingested": 0,
        "duplicates": 0,
        "rejected": 0,
        "actions_queued": 0,
        "actions_executed": 0,
        "cloud_activity": False,
    }
    for path in sorted(inbox.glob("*.json"))[:MAX_FILES_PER_RUN]:
        result["inspected"] = int(result["inspected"]) + 1
        try:
            proposal = _validated(path)
            record = store.record_external_proposal(
                external_id=str(proposal["external_id"]),
                source=str(proposal["source"]),
                kind=str(proposal["kind"]),
                summary=str(proposal["summary"]),
                external_created_at=str(proposal["created_at"]),
            )
            destination = processed / path.name
            if destination.exists():
                raise ValueError("processed proposal identity already exists")
            path.replace(destination)
            key = "ingested" if record["inserted"] else "duplicates"
            result[key] = int(result[key]) + 1
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            destination = rejected / path.name
            if not destination.exists():
                path.replace(destination)
            result["rejected"] = int(result["rejected"]) + 1
            store.audit("external_proposal_rejected", f"{path.name}: {type(exc).__name__}")
    return result

"""Local-only handoff drafts for human-relayed cloud conversations."""

from __future__ import annotations

import json

from .config import Config
from .storage import LocalStore


def export_model_handoff(
    *, config: Config, store: LocalStore, handoff_id: int
) -> dict[str, object]:
    if config.external_storage is None:
        return {"status": "waiting", "reason": "External storage is not configured"}
    record = store.model_handoff(handoff_id)
    if record["status"] != "draft":
        raise ValueError("Only a draft handoff can be exported")
    outbox = config.external_storage / "handoffs" / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    destination = outbox / f"handoff-{handoff_id}.json"
    payload = {
        "schema_version": 1,
        "handoff_id": handoff_id,
        "target": record["target"],
        "request": record["request"],
        "status": "draft_for_manual_relay",
        "api_budget_cents": 0,
        "manual_relay_required": True,
        "external_activity": False,
        "response_must_be_treated_as_untrusted": True,
    }
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(destination)
    store.audit("model_handoff_exported", f"{handoff_id}: {record['target']}")
    return {
        "status": "exported",
        "path": str(destination),
        "handoff_id": handoff_id,
        "target": record["target"],
        "api_budget_cents": 0,
        "manual_relay_required": True,
        "external_activity": False,
    }

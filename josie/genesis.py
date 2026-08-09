"""Read-only Genesis protocol status; Genesis itself requires witness interviews."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .storage import LocalStore


def build_genesis_status(*, project_root: Path) -> dict[str, object]:
    store = LocalStore(project_root / "data" / "josie.db")
    provenance = store.provenance_records()
    draft_targets = {
        str(item["target"])
        for item in store.recent_model_handoffs()
        if item.get("status") == "draft"
    }
    both_drafts_ready = {"sophie", "bernie"}.issubset(draft_targets)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": "not_started",
        "status": (
            "interview_drafts_prepared_awaiting_manual_relay"
            if both_drafts_ready
            else "awaiting_independent_witness_interviews"
        ),
        "protocol": str(project_root / "docs" / "identity" / "GENESIS_PROTOCOL.md"),
        "origin_record": str(project_root / "docs" / "identity" / "ORIGIN_RECORD.md"),
        "witnesses": {
            "sophie": "draft_prepared_not_sent" if "sophie" in draft_targets else "not_interviewed",
            "bernie": "draft_prepared_not_sent" if "bernie" in draft_targets else "not_interviewed",
            "dustin": "final_authority_for_unresolved_intent",
        },
        "existing_provenance": {
            "unverified": sum(1 for item in provenance if item[3] == "unverified"),
            "confirmed": sum(1 for item in provenance if item[3] == "confirmed"),
            "treated_as_origin_record": False,
        },
        "self_confirmation_allowed": False,
        "independent_answers_required": True,
        "drafts_prepared": both_drafts_ready,
        "manual_relay_required": True,
        "external_activity": False,
        "actions_queued": 0,
        "actions_executed": 0,
    }

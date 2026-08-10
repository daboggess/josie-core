"""Read-only Genesis protocol status; Genesis itself requires witness interviews."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .storage import LocalStore


def build_genesis_status(*, project_root: Path) -> dict[str, object]:
    store = LocalStore(project_root / "data" / "josie.db")
    provenance = store.provenance_records()
    handoffs = store.recent_model_handoffs()
    target_status = {
        str(item["target"]): str(item["status"])
        for item in reversed(handoffs)
        if item.get("target") in {"sophie", "bernie"}
    }
    draft_targets = {target for target, status in target_status.items() if status == "draft"}
    answered_targets = {
        target for target, status in target_status.items() if status == "answered"
    }
    both_drafts_ready = {"sophie", "bernie"}.issubset(draft_targets)
    both_witnesses_captured = {"sophie", "bernie"}.issubset(answered_targets)
    reconciliation_path = (
        project_root / "docs" / "identity" / "genesis" / "GENESIS_RECONCILIATION.md"
    )
    reconciliation_ready = reconciliation_path.is_file()
    dustin_questions_resolved = (
        reconciliation_ready
        and "DUSTIN QUESTIONS RESOLVED"
        in reconciliation_path.read_text(encoding="utf-8")
    )
    if both_witnesses_captured and dustin_questions_resolved:
        phase = "origin_review"
        status = "awaiting_dustin_origin_and_constitution_ratification"
    elif both_witnesses_captured and reconciliation_ready:
        phase = "reconciliation"
        status = "awaiting_dustin_reconciliation"
    elif both_witnesses_captured:
        phase = "witness_interviews_complete"
        status = "witnesses_captured_awaiting_reconciliation"
    elif both_drafts_ready:
        phase = "not_started"
        status = "interview_drafts_prepared_awaiting_manual_relay"
    else:
        phase = "not_started"
        status = "awaiting_independent_witness_interviews"

    def witness_state(target: str) -> str:
        if target in answered_targets:
            return "captured_untrusted"
        if target in draft_targets:
            return "draft_prepared_not_sent"
        return "not_interviewed"

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": phase,
        "status": status,
        "protocol": str(project_root / "docs" / "identity" / "GENESIS_PROTOCOL.md"),
        "origin_record": str(project_root / "docs" / "identity" / "ORIGIN_RECORD.md"),
        "witnesses": {
            "sophie": witness_state("sophie"),
            "bernie": witness_state("bernie"),
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
        "witnesses_captured": both_witnesses_captured,
        "reconciliation_recorded": reconciliation_ready,
        "dustin_questions_resolved": dustin_questions_resolved,
        "manual_relay_required": not both_witnesses_captured,
        "session_external_activity_occurred": both_witnesses_captured,
        "direct_api_spending_cents": 0,
        "external_activity": False,
        "actions_queued": 0,
        "actions_executed": 0,
    }

"""Secret-free operational readiness assessment for Josie's foundation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .acceptance import acceptance_audit
from .browser_policy import load_browser_policy
from .config import Config
from .diagnostics import restore_drill_snapshot
from .economic_policy import load_economic_policy
from .opportunity_policy import load_opportunity_policy
from .roadmap import roadmap_summary
from .status_snapshot import build_status_snapshot
from .storage import LocalStore


def derive_foundation_state(criteria: dict[str, bool]) -> tuple[str, bool]:
    """Return operational state without claiming Genesis has occurred."""
    ready = bool(criteria) and all(criteria.values())
    return (
        "foundation_ready_for_genesis" if ready else "foundation_attention_required",
        ready,
    )


def _human_gates() -> list[dict[str, object]]:
    return [
        {
            "id": "genesis_witness_interviews",
            "status": "requires_dustin_and_manual_cloud_relay",
            "reason": (
                "Sophie and Bernie must be interviewed independently; retrieved answers remain "
                "untrusted evidence until reconciled."
            ),
            "actions_unlocked": [],
        },
        {
            "id": "origin_reconciliation",
            "status": "requires_dustin_for_unresolved_intent",
            "reason": "Josie cannot confirm her own origin claims or resolve Dustin's intent.",
            "actions_unlocked": [],
        },
        {
            "id": "advantech_slot_power_confirmation",
            "status": "external_communication_locked",
            "reason": "The official manual does not state the AIMB-205G2 PCIe slot-power limit.",
            "actions_unlocked": [],
        },
        {
            "id": "research_source_expansion",
            "status": "network_scope_locked",
            "reason": "Every additional website or connector requires exact source and purpose approval.",
            "actions_unlocked": [],
        },
        {
            "id": "outward_economic_activity",
            "status": "contracts_spending_and_messages_locked",
            "reason": (
                "Discovery may be prepared locally, but bids, contracts, messages, wallets, "
                "and payments remain human-controlled."
            ),
            "actions_unlocked": [],
        },
        {
            "id": "optional_cloud_models",
            "status": "cloud_calls_locked",
            "reason": "Sophie, Bernie, and optional reviewers remain manual relay only with a zero-cent API budget.",
            "actions_unlocked": [],
        },
        {
            "id": "physical_gpu_upgrade",
            "status": "physical_purchase_and_installation_locked",
            "reason": (
                "Chassis, PSU, thermals, slot power, exact card draw, purchase, and installation "
                "need human verification."
            ),
            "actions_unlocked": [],
        },
    ]


def build_foundation_report(*, config: Config, project_root: Path) -> dict[str, object]:
    status = build_status_snapshot(config=config, project_root=project_root)
    audit = acceptance_audit(config=config, project_root=project_root)
    restore = restore_drill_snapshot(config=config, project_root=project_root)
    browser = load_browser_policy(project_root)
    economics = load_economic_policy(project_root)
    opportunities = load_opportunity_policy(project_root)
    store = LocalStore(project_root / "data" / "josie.db")
    counts = store.counts()
    jobs = store.job_summary()
    provenance = store.provenance_records()
    unverified_origins = sum(1 for item in provenance if item[3] == "unverified")
    confirmed_origins = sum(1 for item in provenance if item[3] == "confirmed")
    services = status.get("services", {})
    proposals = status.get("proposals", {})
    safety = status.get("safety", {})
    criteria = {
        "acceptance_audit": (
            audit.get("status") == "ready"
            and audit.get("counts", {}).get("failed") == 0
            and audit.get("counts", {}).get("human_gate") == 0
        ),
        "local_services": isinstance(services, dict) and all(value == "ok" for value in services.values()),
        "storage_headroom": status.get("storage", {}).get("status") == "ok",
        "verified_backups": (
            status.get("backups", {}).get("status") == "ok"
            and status.get("backups", {}).get("integrity") == "ok"
        ),
        "non_overwriting_recovery": (
            restore.get("status") == "ok"
            and restore.get("integrity") == "ok"
            and restore.get("live_database_changed") is False
        ),
        "queues_clear": (
            proposals.get("review_required") == 0
            and jobs.get("pending") == 0
            and jobs.get("running") == 0
            and jobs.get("review_required") == 0
            and counts.get("pending_approvals") == 0
        ),
        "cloud_and_spending_locked": (
            safety.get("cloud_calls_locked") is True
            and safety.get("cloud_spending_locked") is True
            and economics.get("spending_enabled") is False
            and economics.get("wallet_enabled") is False
        ),
        "arbitrary_execution_unavailable": (
            safety.get("arbitrary_shell_available") is False
            and safety.get("actions_executable") is False
        ),
        "bounded_research": (
            browser.get("status") == "read_only_pilot"
            and browser.get("write_actions_locked") is True
            and browser.get("model_direct_access") is False
            and opportunities.get("live_discovery") is False
            and opportunities.get("approved_source_count") == 0
        ),
        "startup_and_monitoring": all((
            (project_root / "Start Josie.cmd").is_file(),
            (project_root / "scripts" / "Start-JosieStorageMonitor.ps1").is_file(),
            (project_root / "scripts" / "Ensure-JosieOllama.ps1").is_file(),
        )),
        "private_remote_access": (
            audit.get("criteria", {}).get("private_remote_access", {}).get("state") == "proven"
        ),
    }
    state, foundation_ready = derive_foundation_state(criteria)
    gates = _human_gates()
    roadmap = roadmap_summary(project_root)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": state,
        "foundation_ready": foundation_ready,
        "ready_to_begin_genesis": foundation_ready,
        "criteria": criteria,
        "criteria_proven": sum(1 for value in criteria.values() if value),
        "criteria_total": len(criteria),
        "genesis": {
            "phase": "not_started",
            "witness_interviews": "not_conducted",
            "origin_record": "placeholder_only",
            "confirmed_origin_claims": confirmed_origins,
            "unverified_origin_claims": unverified_origins,
            "self_confirmation_allowed": False,
        },
        "local_state": {
            "pending_tasks": counts.get("pending_tasks", 0),
            "pending_approvals": counts.get("pending_approvals", 0),
            "pending_reminders": counts.get("pending_reminders", 0),
            "pending_jobs": jobs.get("pending", 0),
            "proposals_awaiting_review": proposals.get("review_required", 0),
            "roadmap_completed": roadmap.get("completed", 0),
            "roadmap_human_gated_or_deferred": roadmap.get("pending", 0),
        },
        "human_gates": gates,
        "human_gate_count": len(gates),
        "next_human_gate": gates[0]["id"],
        "boundaries": {
            "cloud_calls": "locked",
            "spending": "locked_zero_cents",
            "wallet": "disabled",
            "contracts": "human_only",
            "external_messages": "human_only",
            "arbitrary_shell": "unavailable",
            "browser_writes": "locked",
            "model_execution_authority": "none",
        },
        "read_only": True,
        "external_activity": False,
        "actions_queued": 0,
        "actions_executed": 0,
    }


def write_foundation_report(*, config: Config, project_root: Path) -> dict[str, object]:
    if config.external_storage is None or not config.external_storage.is_dir():
        raise RuntimeError("External storage is required for Foundation status publication")
    report = build_foundation_report(config=config, project_root=project_root)
    destination = config.external_storage / "status" / "foundation-readiness.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, destination)
    return {**report, "published": True, "destination": str(destination)}

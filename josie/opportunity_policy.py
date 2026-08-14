"""Fail-closed policy for future economic opportunity discovery."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_OUTPUTS = {
    "local_research_note", "profit_estimate", "risk_estimate", "human_review_proposal",
}
REQUIRED_PROHIBITIONS = {
    "account_creation", "authentication", "application_submission", "bid_submission",
    "contract_acceptance", "external_message", "file_upload", "identity_verification",
    "payment", "purchase", "wallet_activity",
}


def load_opportunity_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "opportunity-sources.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 2 or raw.get("default") != "deny":
        raise ValueError("Opportunity policy must use schema 2 and default deny")
    if raw.get("enabled") is not False or raw.get("live_discovery") is not False:
        raise ValueError("Live opportunity discovery requires a separate human approval")
    approved_sources = raw.get("approved_sources")
    if not isinstance(approved_sources, list) or len(approved_sources) != 1:
        raise ValueError("Opportunity policy must contain the one selected staged source")
    source = approved_sources[0]
    expected_source = {
        "source_id": "ebay_browse_api",
        "name": "eBay Browse API",
        "decision": "approved_first_source",
        "status": "staged_not_active",
        "approved_by": "Dustin Boggess",
        "approved_on": "2026-08-14",
        "purpose": (
            "Read-only discovery of active hardware listings for local normalization, "
            "deduplication, scoring, and human review."
        ),
        "network_enabled": False,
        "account_connected": False,
        "credentials_present": False,
        "live_calls_authorized": False,
        "user_authentication_allowed": False,
        "purchase_or_bidding_allowed": False,
        "policy_record": "config/ebay-source.json",
    }
    if source != expected_source:
        raise ValueError("Selected opportunity source is not safely staged")
    categories = raw.get("research_categories")
    if not isinstance(categories, list) or not categories or not all(
        isinstance(item, str) and item for item in categories
    ):
        raise ValueError("Opportunity research categories are invalid")
    outputs = raw.get("allowed_output")
    if not isinstance(outputs, list) or set(outputs) != REQUIRED_OUTPUTS:
        raise ValueError("Opportunity output boundary is incomplete")
    prohibited = raw.get("prohibited_actions")
    if not isinstance(prohibited, list) or set(prohibited) != REQUIRED_PROHIBITIONS:
        raise ValueError("Opportunity action boundary is incomplete")
    if raw.get("human_approval_required_to_add_source") is not True:
        raise ValueError("Opportunity sources must require human approval")
    if raw.get("human_approval_required_to_activate_source") is not True:
        raise ValueError("Opportunity source activation must require human approval")
    if raw.get("model_may_modify_policy") is not False:
        raise ValueError("Models may not modify opportunity policy")
    if raw.get("external_activity") is not False:
        raise ValueError("Opportunity policy must prove zero external activity")
    if raw.get("transactions_executed") != 0 or raw.get("contracts_accepted") != 0:
        raise ValueError("Opportunity policy must prove zero economic execution")
    return {
        "status": "source_selected_not_active",
        "enabled": False,
        "live_discovery": False,
        "approved_sources": approved_sources,
        "approved_source_count": 1,
        "research_categories": categories,
        "allowed_output": outputs,
        "prohibited_actions": prohibited,
        "human_approval_required_to_add_source": True,
        "human_approval_required_to_activate_source": True,
        "model_may_modify_policy": False,
        "external_activity": False,
        "transactions_executed": 0,
        "contracts_accepted": 0,
    }

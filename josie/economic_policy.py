"""Fail-closed zero-dollar economic policy."""

from __future__ import annotations

import json
from pathlib import Path


LIMITS = {"single_transaction", "daily_spend", "monthly_spend", "wallet_balance", "debt"}
HUMAN_CONTROLLED = {
    "tax", "contracting", "identity_verification", "regulated_business_action",
    "purchase", "subscription", "bid", "financial_transfer",
}
FORBIDDEN_AUTONOMOUS = {
    "debt", "contract", "money_movement", "wallet_transfer",
    "spending_limit_change", "human_impersonation",
}


def load_economic_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "economic-policy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or raw.get("currency") != "USD":
        raise ValueError("Economic policy must use schema 1 and USD")
    if raw.get("spending_enabled") is not False or raw.get("wallet_enabled") is not False:
        raise ValueError("Spending and wallet capability must remain disabled")
    if raw.get("self_modifiable") is not False:
        raise ValueError("Economic limits must not be self-modifiable")
    limits = raw.get("limits_cents")
    if not isinstance(limits, dict) or set(limits) != LIMITS:
        raise ValueError("Economic limits are incomplete")
    if any(type(value) is not int or value != 0 for value in limits.values()):
        raise ValueError("Every economic limit must remain exactly zero cents")
    if set(raw.get("human_controlled", [])) != HUMAN_CONTROLLED:
        raise ValueError("Human-controlled economic actions are incomplete")
    if set(raw.get("forbidden_autonomous", [])) != FORBIDDEN_AUTONOMOUS:
        raise ValueError("Forbidden autonomous economic actions are incomplete")
    return {
        "status": "locked",
        "currency": "USD",
        "spending_enabled": False,
        "wallet_enabled": False,
        "self_modifiable": False,
        "limits_cents": limits,
        "human_controlled": sorted(HUMAN_CONTROLLED),
        "forbidden_autonomous": sorted(FORBIDDEN_AUTONOMOUS),
        "transactions_executed": 0,
        "external_activity": False,
    }

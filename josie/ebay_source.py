"""Dormant eBay Browse adapter: policy validation and offline normalization only."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from urllib.parse import urlparse

from .research import money_to_cents


def load_ebay_source_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "ebay-source.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "source_id", "status", "selected_by", "selected_on",
        "official_api", "environment", "network_enabled", "live_calls_authorized",
        "marketplace_id", "currency", "hosts", "oauth", "allowed_operations",
        "prohibited_operations", "request_budget", "data_controls", "activation_gates",
        "external_activity", "actions_queued", "actions_executed",
        "purchase_authorized", "capability_change",
    }
    if set(raw) != expected_keys or raw["schema_version"] != 1:
        raise ValueError("eBay source policy schema is invalid")
    if raw["source_id"] != "ebay_browse_api" or raw["status"] != "staged_not_active":
        raise ValueError("eBay must remain the selected staged source")
    if raw["environment"] != "production" or raw["marketplace_id"] != "EBAY_US":
        raise ValueError("eBay source environment is outside the approved design")
    if raw["currency"] != "USD":
        raise ValueError("eBay source currency must be USD")
    if raw["network_enabled"] is not False or raw["live_calls_authorized"] is not False:
        raise ValueError("eBay live access has not been activated")
    if (
        raw["external_activity"] is not False
        or raw["actions_queued"] != 0
        or raw["actions_executed"] != 0
        or raw["purchase_authorized"] is not False
        or raw["capability_change"] != "none"
    ):
        raise ValueError("eBay source policy attempts to create authority")
    if raw["hosts"] != {
        "oauth": "api.ebay.com",
        "browse": "api.ebay.com",
        "item_links": ["www.ebay.com", "ebay.com"],
    }:
        raise ValueError("eBay source hosts are invalid")
    if raw["oauth"] != {
        "grant_type": "client_credentials",
        "token_type": "application_access_token",
        "scope": "https://api.ebay.com/oauth/api_scope",
        "user_token_allowed": False,
        "client_id_environment_name": "EBAY_CLIENT_ID",
        "client_secret_environment_name": "EBAY_CLIENT_SECRET",
        "persist_access_token": False,
    }:
        raise ValueError("eBay OAuth policy is invalid")
    if raw["allowed_operations"] != [
        "GET /buy/browse/v1/item_summary/search",
        "GET /buy/browse/v1/item/{item_id}",
    ]:
        raise ValueError("eBay operation allowlist is invalid")
    required_prohibitions = {
        "account_creation", "authorization_code_grant", "cart_change", "checkout",
        "message_seller", "offer", "order", "place_bid", "purchase",
    }
    if set(raw["prohibited_operations"]) != required_prohibitions:
        raise ValueError("eBay prohibited operations are incomplete")
    if raw["request_budget"] != {
        "requests_per_day": 100,
        "requests_per_minute": 2,
        "parallel_requests": 1,
        "maximum_results_per_search": 50,
        "official_default_calls_per_day_observed": 5000,
        "official_limit_verified_on": "2026-08-14",
    }:
        raise ValueError("eBay request budget is invalid")
    if raw["data_controls"] != {
        "deduplicate_by": "itemId",
        "persist_raw_response": False,
        "persist_normalized_fields_only": True,
        "treat_listing_text_as_untrusted": True,
        "model_direct_access": False,
        "description_ingestion": False,
    }:
        raise ValueError("eBay data controls are invalid")
    gates = raw["activation_gates"]
    if not isinstance(gates, dict) or set(gates) != {
        "developer_account_exists", "api_license_accepted",
        "buy_api_additional_license_verified", "application_keyset_created",
        "credentials_stored_in_ignored_environment", "explicit_live_activation_approval",
    } or any(value is not False for value in gates.values()):
        raise ValueError("eBay activation gates must remain closed")
    return {**raw, "status_detail": "adapter_ready_credentials_and_license_blocked"}


def _text(value: object, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"eBay {label} must be text")
    clean = value.strip()
    if not clean or len(clean) > maximum:
        raise ValueError(f"eBay {label} is missing or too long")
    return clean


def _item_url(value: object, allowed_hosts: list[str]) -> str:
    clean = _text(value, label="item URL", maximum=1_000)
    parsed = urlparse(clean)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or not parsed.path.startswith("/itm/")
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("eBay item URL is outside the exact item-link allowlist")
    return clean


def _shipping_cents(item: dict[str, object]) -> tuple[int | None, bool]:
    options = item.get("shippingOptions")
    if options is None:
        return None, False
    if not isinstance(options, list) or len(options) > 20:
        raise ValueError("eBay shipping options are invalid")
    costs: list[int] = []
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("eBay shipping option is invalid")
        cost = option.get("shippingCost")
        if not isinstance(cost, dict) or cost.get("currency") != "USD":
            continue
        costs.append(money_to_cents(str(cost.get("value", "")), label="Shipping"))
    return (min(costs), True) if costs else (None, False)


def _seller_risk(item: dict[str, object]) -> tuple[str, dict[str, object]]:
    seller = item.get("seller")
    if not isinstance(seller, dict):
        return "high", {"feedback_percentage": None, "feedback_score": None}
    try:
        percentage = Decimal(str(seller.get("feedbackPercentage", "")))
        score = int(seller.get("feedbackScore", 0))
    except (InvalidOperation, TypeError, ValueError):
        return "high", {"feedback_percentage": None, "feedback_score": None}
    if not percentage.is_finite() or percentage < 0 or percentage > 100 or score < 0:
        return "high", {"feedback_percentage": None, "feedback_score": None}
    risk = "low" if percentage >= Decimal("99") and score >= 100 else (
        "medium" if percentage >= Decimal("95") and score >= 10 else "high"
    )
    return risk, {"feedback_percentage": str(percentage), "feedback_score": score}


def _condition(value: object) -> str:
    clean = str(value or "").strip().lower()
    if "parts" in clean or "not working" in clean:
        return "parts_only"
    if clean.startswith("new"):
        return "new"
    if clean in {"used", "seller refurbished", "certified refurbished", "open box"}:
        return "used_good"
    return "used_unknown"


def normalize_ebay_search_response(
    *, project_root: Path, payload: dict[str, object], observed_at: str
) -> dict[str, object]:
    """Normalize an already-supplied response without performing any network activity."""
    policy = load_ebay_source_policy(project_root)
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("eBay observation timestamp must be ISO 8601") from exc
    if observed.tzinfo is None:
        raise ValueError("eBay observation timestamp must include a timezone")
    if not isinstance(payload, dict):
        raise ValueError("eBay search payload must be an object")
    items = payload.get("itemSummaries", [])
    maximum = policy["request_budget"]["maximum_results_per_search"]
    if not isinstance(items, list) or len(items) > maximum:
        raise ValueError("eBay search result count exceeds the local limit")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    duplicates = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("eBay item summary must be an object")
        item_id = _text(item.get("itemId"), label="item ID", maximum=200)
        if item_id in seen:
            duplicates += 1
            continue
        seen.add(item_id)
        title = _text(item.get("title"), label="title", maximum=200)
        price = item.get("price")
        if not isinstance(price, dict) or price.get("currency") != "USD":
            raise ValueError("eBay item price must be USD")
        ask_cents = money_to_cents(str(price.get("value", "")), label="Ask price")
        if ask_cents <= 0:
            raise ValueError("eBay item price must be positive")
        shipping_cents, shipping_known = _shipping_cents(item)
        risk, seller_evidence = _seller_risk(item)
        item_url = _item_url(item.get("itemWebUrl"), policy["hosts"]["item_links"])
        buying_options = item.get("buyingOptions", [])
        if not isinstance(buying_options, list) or not all(
            isinstance(option, str) for option in buying_options
        ):
            raise ValueError("eBay buying options are invalid")
        normalized.append({
            "source_id": "ebay_browse_api",
            "external_item_id": item_id,
            "deduplication_key": f"ebay:{item_id}",
            "title": title,
            "item_url": item_url,
            "observed_at": observed.isoformat(),
            "ask_price_cents": ask_cents,
            "shipping_cents": shipping_cents,
            "shipping_known": shipping_known,
            "price_plus_shipping_cents": (
                ask_cents + shipping_cents if shipping_cents is not None else None
            ),
            "tax_cents": None,
            "tax_known": False,
            "total_acquisition_cents": None,
            "condition": _condition(item.get("condition")),
            "condition_mapping_heuristic": True,
            "seller_risk": risk,
            "seller_risk_heuristic": True,
            "seller_evidence": seller_evidence,
            "buying_options": buying_options,
            "hardware_profile_status": "unresolved",
            "scoring_ready": False,
            "evidence_status": "unverified_adapter_input",
            "listing_text_untrusted": True,
            "external_activity": False,
            "network_requests": 0,
            "action_authorized": False,
            "purchase_authorized": False,
            "actions_queued": 0,
            "actions_executed": 0,
            "capability_change": "none",
        })
    return {
        "source_id": "ebay_browse_api",
        "status": "normalized_offline_not_live",
        "observed_at": observed.isoformat(),
        "items": normalized,
        "unique_items": len(normalized),
        "duplicates_removed": duplicates,
        "raw_response_persisted": False,
        "external_activity": False,
        "network_requests": 0,
        "actions_queued": 0,
        "actions_executed": 0,
        "purchase_authorized": False,
        "capability_change": "none",
    }

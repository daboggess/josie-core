"""Offline hardware-deal scoring with evidence and zero purchase authority."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
from urllib.parse import urlparse

from .evidence_policy import evaluate_claim_evidence, load_evidence_policy
from .research import money_to_cents
from .storage import LocalStore


COMPATIBILITY = {"compatible", "needs_review", "unknown", "incompatible"}
CONDITIONS = {"new", "used_good", "used_unknown", "parts_only"}
SELLER_RISKS = {"low", "medium", "high"}
MANUAL_DEAL_FORM_FIELDS = frozenset({
    "title",
    "source_reference",
    "observed_at",
    "ask_price",
    "shipping",
    "tax",
    "required_platform_cost",
    "benchmark_index",
    "vram_gb",
    "power_watts",
    "compatibility",
    "condition",
    "seller_risk",
    "notes",
})


def load_deal_scoring_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "deal-scoring-policy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version", "status", "weights", "reference_benchmark_per_dollar",
        "vram_reference_gb", "compatibility_points", "condition_points",
        "risk_penalty", "power_penalty", "thresholds", "live_discovery",
        "external_activity", "action_authorized", "purchase_authorized",
        "capability_change",
    }
    if set(raw) != expected or raw["schema_version"] != 1:
        raise ValueError("Deal scoring policy schema is invalid")
    if raw["status"] != "local_research_only":
        raise ValueError("Deal scoring must remain research-only")
    if (
        raw["live_discovery"] is not False
        or raw["external_activity"] is not False
        or raw["action_authorized"] is not False
        or raw["purchase_authorized"] is not False
        or raw["capability_change"] != "none"
    ):
        raise ValueError("Deal scoring policy attempts to create external authority")
    weights = raw["weights"]
    if not isinstance(weights, dict) or weights != {
        "price_performance": 40,
        "vram": 20,
        "compatibility": 20,
        "condition": 10,
        "evidence": 10,
    }:
        raise ValueError("Deal scoring weights are outside the governed model")
    if raw["compatibility_points"] != {
        "compatible": 20, "needs_review": 8, "unknown": 0, "incompatible": 0
    }:
        raise ValueError("Deal compatibility scoring is invalid")
    if raw["condition_points"] != {
        "new": 10, "used_good": 8, "used_unknown": 3, "parts_only": 0
    }:
        raise ValueError("Deal condition scoring is invalid")
    if raw["risk_penalty"] != {"low": 0, "medium": 5, "high": 15}:
        raise ValueError("Deal risk scoring is invalid")
    power = raw["power_penalty"]
    if power != {"free_watts": 200, "maximum_watts": 500, "maximum_points": 10}:
        raise ValueError("Deal power scoring is invalid")
    if raw["thresholds"] != {"candidate_for_human_review": 70, "watchlist": 50}:
        raise ValueError("Deal recommendation thresholds are invalid")
    if raw["reference_benchmark_per_dollar"] != 0.25 or raw["vram_reference_gb"] != 24:
        raise ValueError("Deal scoring references are invalid")
    return {**raw, "policy_status": "enforced_local_only"}


def _decimal(value: str, *, label: str, minimum: Decimal, maximum: Decimal) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not result.is_finite() or result < minimum or result > maximum:
        raise ValueError(f"{label} is outside the permitted research range")
    return result


def _source_reference(value: str) -> str:
    clean = value.strip()
    if not clean or len(clean) > 500:
        raise ValueError("Deal source reference must contain 1 to 500 characters")
    if "://" in clean:
        parsed = urlparse(clean)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Deal source URL is invalid or contains credentials")
    return clean


def evaluate_deal_candidate(
    *,
    project_root: Path,
    title: str,
    source_reference: str,
    source_kind: str,
    observed_at: str,
    ask_price: str,
    shipping: str,
    tax: str,
    required_platform_cost: str,
    benchmark_index: str,
    vram_gb: str,
    power_watts: int,
    compatibility: str,
    condition: str,
    seller_risk: str,
    notes: str,
    as_of: datetime | None = None,
) -> dict[str, object]:
    clean_title = title.strip()
    clean_notes = notes.strip()
    if not clean_title or len(clean_title) > 200:
        raise ValueError("Deal title must contain 1 to 200 characters")
    if not clean_notes or len(clean_notes) > 2_000:
        raise ValueError("Deal notes must contain 1 to 2000 characters")
    clean_source = _source_reference(source_reference)
    if compatibility not in COMPATIBILITY:
        raise ValueError("Deal compatibility status is invalid")
    if condition not in CONDITIONS:
        raise ValueError("Deal condition is invalid")
    if seller_risk not in SELLER_RISKS:
        raise ValueError("Deal seller risk is invalid")
    if not isinstance(power_watts, int) or not 0 <= power_watts <= 2_000:
        raise ValueError("Deal power must be 0 to 2000 watts")
    costs = {
        "ask_price_cents": money_to_cents(ask_price, label="Ask price"),
        "shipping_cents": money_to_cents(shipping, label="Shipping"),
        "tax_cents": money_to_cents(tax, label="Tax"),
        "required_platform_cost_cents": money_to_cents(
            required_platform_cost, label="Required platform cost"
        ),
    }
    total_cents = sum(costs.values())
    if total_cents <= 0:
        raise ValueError("Deal total acquisition cost must be positive")
    benchmark = _decimal(
        benchmark_index, label="Benchmark index", minimum=Decimal("0.01"),
        maximum=Decimal("1000000"),
    )
    vram = _decimal(
        vram_gb, label="VRAM", minimum=Decimal("0"), maximum=Decimal("1024")
    )
    policy = load_deal_scoring_policy(project_root)
    evidence = evaluate_claim_evidence(
        policy=load_evidence_policy(project_root), stability="unstable",
        source_kind=source_kind, observed_at=observed_at, as_of=as_of,
    )
    total_dollars = Decimal(total_cents) / 100
    benchmark_per_dollar = benchmark / total_dollars
    ppp_points = min(
        Decimal("40"),
        benchmark_per_dollar
        / Decimal(str(policy["reference_benchmark_per_dollar"]))
        * Decimal("40"),
    )
    vram_points = min(
        Decimal("20"),
        vram / Decimal(str(policy["vram_reference_gb"])) * Decimal("20"),
    )
    compatibility_points = Decimal(policy["compatibility_points"][compatibility])
    condition_points = Decimal(policy["condition_points"][condition])
    evidence_points = Decimal("10") if evidence["verified_for_analysis"] else Decimal("0")
    risk_penalty = Decimal(policy["risk_penalty"][seller_risk])
    power = policy["power_penalty"]
    if power_watts <= power["free_watts"]:
        power_penalty = Decimal("0")
    else:
        span = power["maximum_watts"] - power["free_watts"]
        power_penalty = min(
            Decimal(power["maximum_points"]),
            Decimal(power_watts - power["free_watts"])
            / Decimal(span)
            * Decimal(power["maximum_points"]),
        )
    raw_score = (
        ppp_points + vram_points + compatibility_points + condition_points
        + evidence_points - risk_penalty - power_penalty
    )
    score = max(Decimal("0"), min(Decimal("100"), raw_score)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    if compatibility == "incompatible":
        recommendation = "reject_incompatible"
    elif not evidence["verified_for_analysis"]:
        recommendation = "verify_before_review"
    elif seller_risk == "high":
        recommendation = "high_risk_hold"
    elif score >= Decimal(policy["thresholds"]["candidate_for_human_review"]):
        recommendation = "candidate_for_human_review"
    elif score >= Decimal(policy["thresholds"]["watchlist"]):
        recommendation = "watchlist"
    else:
        recommendation = "low_priority"
    uncertainty: list[str] = []
    if not evidence["verified_for_analysis"]:
        uncertainty.append("current_listing_evidence_required")
    if compatibility in {"unknown", "needs_review"}:
        uncertainty.append("compatibility_not_confirmed")
    if condition in {"used_unknown", "parts_only"}:
        uncertainty.append("condition_risk")
    if seller_risk != "low":
        uncertainty.append("seller_risk")
    return {
        "title": clean_title,
        "source_reference": clean_source,
        "source_kind": source_kind,
        "observed_at": evidence["observed_at"],
        "notes": clean_notes,
        "costs": {**costs, "total_acquisition_cents": total_cents},
        "benchmark_index": str(benchmark.normalize()),
        "benchmark_per_dollar": float(benchmark_per_dollar.quantize(Decimal("0.0001"))),
        "vram_gb": str(vram.normalize()),
        "power_watts": power_watts,
        "compatibility": compatibility,
        "condition": condition,
        "seller_risk": seller_risk,
        "score_breakdown": {
            "price_performance": float(ppp_points.quantize(Decimal("0.1"))),
            "vram": float(vram_points.quantize(Decimal("0.1"))),
            "compatibility": int(compatibility_points),
            "condition": int(condition_points),
            "evidence": int(evidence_points),
            "risk_penalty": float(risk_penalty),
            "power_penalty": float(power_penalty.quantize(Decimal("0.1"))),
        },
        "research_score": float(score),
        "recommendation": recommendation,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "heuristic_not_market_truth": True,
        "external_activity": False,
        "action_authorized": False,
        "purchase_authorized": False,
        "capability_change": "none",
        "actions_queued": 0,
        "actions_executed": 0,
    }


def score_and_record_deal(*, store: LocalStore, **kwargs) -> dict[str, object]:
    result = evaluate_deal_candidate(**kwargs)
    stored = store.record_deal_candidate(result)
    return {**result, "candidate_id": stored["candidate_id"], "created_at": stored["created_at"]}


def score_manual_deal_form(
    *,
    store: LocalStore,
    project_root: Path,
    fields: dict[str, str],
    as_of: datetime | None = None,
) -> dict[str, object]:
    """Score an exact local-form payload as unverified user-supplied evidence."""
    if not isinstance(fields, dict) or set(fields) != MANUAL_DEAL_FORM_FIELDS:
        raise ValueError("Manual deal form fields do not match the governed schema")
    if not all(isinstance(value, str) for value in fields.values()):
        raise ValueError("Manual deal form values must be text")
    power_text = fields["power_watts"].strip()
    if not power_text.isdecimal():
        raise ValueError("Deal power must be a whole number of watts")
    return score_and_record_deal(
        store=store,
        project_root=project_root,
        title=fields["title"],
        source_reference=fields["source_reference"],
        source_kind="user_supplied",
        observed_at=fields["observed_at"],
        ask_price=fields["ask_price"],
        shipping=fields["shipping"],
        tax=fields["tax"],
        required_platform_cost=fields["required_platform_cost"],
        benchmark_index=fields["benchmark_index"],
        vram_gb=fields["vram_gb"],
        power_watts=int(power_text),
        compatibility=fields["compatibility"],
        condition=fields["condition"],
        seller_risk=fields["seller_risk"],
        notes=fields["notes"],
        as_of=as_of,
    )

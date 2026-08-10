"""Deterministic, fail-closed evidence gate for current and stable claims."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


ALLOWED_SOURCE_KINDS = {
    "canonical_versioned",
    "primary_authoritative",
    "direct_system_observation",
    "model_output",
    "retrieved_memory",
    "secondary",
    "unknown",
    "user_supplied",
}


def load_evidence_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "evidence-policy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version", "default", "model_consensus_sufficient",
        "retrieved_memory_sufficient", "external_action_authority",
        "stability_rules", "untrusted_source_kinds", "unstable_topics",
        "capability_change",
    }
    if set(raw) != expected or raw["schema_version"] != 1:
        raise ValueError("Evidence policy schema is invalid")
    if raw["default"] != "verification_required":
        raise ValueError("Evidence policy must fail closed")
    if (
        raw["model_consensus_sufficient"] is not False
        or raw["retrieved_memory_sufficient"] is not False
        or raw["external_action_authority"] is not False
        or raw["capability_change"] != "none"
    ):
        raise ValueError("Evidence policy attempts to create authority")
    rules = raw["stability_rules"]
    if not isinstance(rules, dict) or set(rules) != {"stable", "unstable"}:
        raise ValueError("Evidence stability rules are invalid")
    normalized_rules: dict[str, dict[str, object]] = {}
    for stability, limit in (("unstable", 168), ("stable", 17_520)):
        rule = rules[stability]
        if not isinstance(rule, dict) or set(rule) != {
            "max_age_hours", "accepted_source_kinds"
        }:
            raise ValueError("Evidence stability rule schema is invalid")
        hours = rule["max_age_hours"]
        kinds = rule["accepted_source_kinds"]
        if (
            not isinstance(hours, int)
            or not 1 <= hours <= limit
            or not isinstance(kinds, list)
            or not kinds
            or not set(kinds).issubset(ALLOWED_SOURCE_KINDS)
        ):
            raise ValueError("Evidence stability rule exceeds its governed limits")
        normalized_rules[stability] = {
            "max_age_hours": hours,
            "accepted_source_kinds": list(kinds),
        }
    untrusted = raw["untrusted_source_kinds"]
    if (
        not isinstance(untrusted, list)
        or set(untrusted) != {
            "model_output", "retrieved_memory", "secondary", "unknown",
            "user_supplied",
        }
    ):
        raise ValueError("Evidence policy untrusted source set is invalid")
    if set(untrusted) & set(normalized_rules["unstable"]["accepted_source_kinds"]):
        raise ValueError("Untrusted evidence cannot verify an unstable claim")
    topics = raw["unstable_topics"]
    if not isinstance(topics, list) or not topics or not all(
        isinstance(item, str) and item.strip() for item in topics
    ):
        raise ValueError("Evidence policy unstable topics are invalid")
    return {
        **raw,
        "stability_rules": normalized_rules,
        "untrusted_source_kinds": list(untrusted),
        "unstable_topics": sorted(set(topics)),
        "status": "enforced_fail_closed",
        "external_activity": False,
        "actions_queued": 0,
        "actions_executed": 0,
    }


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Evidence observation time must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("Evidence observation time must include a timezone")
    return parsed.astimezone(timezone.utc)


def evaluate_claim_evidence(
    *,
    policy: dict[str, object],
    stability: str,
    source_kind: str,
    observed_at: str,
    as_of: datetime | None = None,
) -> dict[str, object]:
    if stability not in {"stable", "unstable"}:
        raise ValueError("Claim stability must be stable or unstable")
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError("Evidence source kind is invalid")
    observed = _timestamp(observed_at)
    now = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if observed > now:
        raise ValueError("Evidence observation time cannot be in the future")
    age_hours = (now - observed).total_seconds() / 3600
    rule = policy["stability_rules"][stability]
    accepted_source = source_kind in set(rule["accepted_source_kinds"])
    fresh = age_hours <= int(rule["max_age_hours"])
    verified = accepted_source and fresh
    reasons: list[str] = []
    if not accepted_source:
        reasons.append("source_kind_not_sufficient")
    if not fresh:
        reasons.append("evidence_stale")
    return {
        "decision": "verified_for_analysis" if verified else "verification_required",
        "verified_for_analysis": verified,
        "stability": stability,
        "source_kind": source_kind,
        "observed_at": observed.isoformat(timespec="seconds"),
        "age_hours": round(age_hours, 3),
        "max_age_hours": int(rule["max_age_hours"]),
        "reasons": reasons,
        "model_consensus_sufficient": False,
        "retrieved_memory_sufficient": False,
        "external_action_authorized": False,
        "capability_change": "none",
        "external_activity": False,
        "actions_queued": 0,
        "actions_executed": 0,
    }

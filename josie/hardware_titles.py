"""Deterministic, non-authorizing title classification for Deal Hunter research."""

from __future__ import annotations

import json
from pathlib import Path
import re


def load_hardware_title_rules(project_root: Path) -> dict[str, object]:
    raw = json.loads(
        (project_root / "config" / "hardware-title-rules.json").read_text(encoding="utf-8")
    )
    if set(raw) != {"schema_version", "status", "input_trust", "profiles", "controls"}:
        raise ValueError("Hardware title-rule schema is invalid")
    if (
        raw["schema_version"] != 1
        or raw["status"] != "research_only_title_candidates"
        or raw["input_trust"] != "untrusted_listing_title"
        or raw["controls"] != {
            "unique_match_required": True,
            "profile_resolved": False,
            "infer_specs_from_title": False,
            "scoring_ready": False,
            "model_direct_access": False,
            "external_activity": False,
            "action_authorized": False,
            "purchase_authorized": False,
            "capability_change": "none",
        }
    ):
        raise ValueError("Hardware title rules attempt to create evidence or authority")
    profiles = raw["profiles"]
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 50:
        raise ValueError("Hardware title profiles are invalid")
    ids: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict) or set(profile) != {
            "profile_id", "canonical_name", "required_term_groups", "forbidden_terms"
        }:
            raise ValueError("Hardware title profile schema is invalid")
        profile_id = profile["profile_id"]
        if (
            not isinstance(profile_id, str)
            or not re.fullmatch(r"[a-z0-9_]{3,80}", profile_id)
            or profile_id in ids
        ):
            raise ValueError("Hardware title profile ID is invalid or duplicated")
        ids.add(profile_id)
        if not isinstance(profile["canonical_name"], str) or not 1 <= len(profile["canonical_name"]) <= 120:
            raise ValueError("Hardware title canonical name is invalid")
        groups = profile["required_term_groups"]
        forbidden = profile["forbidden_terms"]
        if not isinstance(groups, list) or not groups or len(groups) > 10:
            raise ValueError("Hardware title required-term groups are invalid")
        for group in groups:
            if not isinstance(group, list) or not group or len(group) > 10:
                raise ValueError("Hardware title required-term group is invalid")
            if not all(isinstance(term, str) and 1 <= len(term) <= 80 for term in group):
                raise ValueError("Hardware title required term is invalid")
        if not isinstance(forbidden, list) or len(forbidden) > 30 or not all(
            isinstance(term, str) and 1 <= len(term) <= 80 for term in forbidden
        ):
            raise ValueError("Hardware title forbidden terms are invalid")
    return raw


def _normalize_title(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("Hardware listing title must contain 1 to 200 characters")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _contains_phrase(normalized_title: str, phrase: str) -> bool:
    normalized_phrase = _normalize_title(phrase)
    return f" {normalized_phrase} " in f" {normalized_title} "


def classify_hardware_title(*, project_root: Path, title: str) -> dict[str, object]:
    """Suggest at most one identity from title text; never resolve or infer specifications."""
    rules = load_hardware_title_rules(project_root)
    normalized = _normalize_title(title)
    matches: list[dict[str, str]] = []
    rejected_profiles: list[str] = []
    for profile in rules["profiles"]:
        if any(_contains_phrase(normalized, term) for term in profile["forbidden_terms"]):
            rejected_profiles.append(str(profile["profile_id"]))
            continue
        if all(
            any(_contains_phrase(normalized, term) for term in group)
            for group in profile["required_term_groups"]
        ):
            matches.append({
                "profile_id": str(profile["profile_id"]),
                "canonical_name": str(profile["canonical_name"]),
            })
    unique = matches[0] if len(matches) == 1 else None
    status = "possible_unique_title_match" if unique else (
        "ambiguous_title" if len(matches) > 1 else "no_title_match"
    )
    return {
        "status": status,
        "possible_profile": unique,
        "match_count": len(matches),
        "rejected_profile_ids": sorted(rejected_profiles),
        "input_trust": "untrusted_listing_title",
        "profile_resolved": False,
        "specifications_inferred": False,
        "scoring_ready": False,
        "verification_required": True,
        "external_activity": False,
        "network_requests": 0,
        "action_authorized": False,
        "purchase_authorized": False,
        "actions_queued": 0,
        "actions_executed": 0,
        "capability_change": "none",
    }

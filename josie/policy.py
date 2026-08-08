"""Fail-closed machine-readable capability policy."""

from __future__ import annotations

import json
from pathlib import Path


VALID_DECISIONS = {"autonomous", "approval_required", "forbidden"}


def load_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "permissions.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("default") != "forbidden":
        raise ValueError("Permission policy must default to forbidden")
    memberships: dict[str, str] = {}
    for decision in VALID_DECISIONS:
        values = raw.get(decision)
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError(f"Invalid policy list: {decision}")
        for capability in values:
            if capability in memberships:
                raise ValueError(f"Capability appears in multiple policy groups: {capability}")
            memberships[capability] = decision
    return {"path": str(path), "default": "forbidden", "capabilities": memberships}


def permission_for(capability: str, project_root: Path) -> dict[str, str]:
    normalized = capability.strip().lower().replace("-", "_").replace(" ", "_")
    policy = load_policy(project_root)
    memberships = policy["capabilities"]
    assert isinstance(memberships, dict)
    return {
        "capability": normalized,
        "decision": str(memberships.get(normalized, policy["default"])),
        "known": str(normalized in memberships).lower(),
    }

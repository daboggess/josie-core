from __future__ import annotations

from copy import deepcopy


REGISTRY = {
    "coding": {
        "department": "coding", "status": "AVAILABLE", "route": "Supervisor",
        "worker": "Coder Worker v1", "harness": "Goose 1.50.0 primary; OpenCode 1.18.23 fallback",
        "primary_harness": "Goose 1.50.0", "fallback_harness": "OpenCode 1.18.23",
        "harness_type": "coder",
        "profile": "josie-coder", "model": "ollama/qwen3:14b",
        "normal_timeout_seconds": 120,
        "envelope": {
            "strengths": ["bounded targeted coding", "concrete acceptance", "existing tests"],
            "preferred_related_files": [1, 3],
            "risks": ["broad architecture", "unbounded multi-file work"],
            "package_installs": "DENIED_BY_DEFAULT",
            "host_mutation": "DENIED_BY_DEFAULT",
            "supervisor_required": True,
        },
    },
    **{name: {"department": name, "status": "NOT_IMPLEMENTED", "route": None, "worker": None}
       for name in ("research", "image", "marketing", "social")},
}

# Explicit, already-qualified exception paths.  These do not alter the primary
# worker registry and are never selected without a caller naming one.
EXPLICIT_CODING_FALLBACKS = {
    "gemma4:12b": "ollama/gemma4:12b",
    "josie-antigravity-flash": "bridge/josie-antigravity-flash",
    "josie-antigravity-pro": "bridge/josie-antigravity-pro",
}


def registry() -> dict:
    return deepcopy(REGISTRY)


def department(name: str) -> dict:
    if name not in REGISTRY:
        raise KeyError(f"unknown department: {name}")
    return deepcopy(REGISTRY[name])


def explicit_coding_fallback(name: str) -> str:
    try:
        return EXPLICIT_CODING_FALLBACKS[name]
    except KeyError as exc:
        raise KeyError(f"fallback worker is not allowed: {name}") from exc

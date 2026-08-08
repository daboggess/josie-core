"""Explicit tool registry. Arbitrary commands are intentionally unsupported."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import Config
from .diagnostics import (
    external_storage_snapshot, health_check, memory_export_snapshot, recovery_snapshot,
    repository_snapshot, restore_drill_snapshot, storage_snapshot, system_snapshot, uptime_snapshot,
)

Tool = Callable[..., dict[str, object]]

_ALLOWED_TOOLS: dict[str, Tool] = {
    "health": health_check,
    "memory-export": memory_export_snapshot,
    "external-storage": external_storage_snapshot,
    "repository": repository_snapshot,
    "recovery": recovery_snapshot,
    "restore-drill": restore_drill_snapshot,
    "storage": storage_snapshot,
    "system": system_snapshot,
    "uptime": uptime_snapshot,
}


def available_tools() -> tuple[str, ...]:
    return tuple(sorted(_ALLOWED_TOOLS))


def run_tool(name: str, *, config: Config, project_root: Path) -> dict[str, Any]:
    try:
        tool = _ALLOWED_TOOLS[name]
    except KeyError as exc:
        raise ValueError(f"Tool is not allowed: {name}") from exc
    return tool(config=config, project_root=project_root)

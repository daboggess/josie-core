"""Explicit tool registry. Arbitrary commands are intentionally unsupported."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import Config
from .diagnostics import health_check

Tool = Callable[..., dict[str, object]]

_ALLOWED_TOOLS: dict[str, Tool] = {
    "health": health_check,
}


def available_tools() -> tuple[str, ...]:
    return tuple(sorted(_ALLOWED_TOOLS))


def run_tool(name: str, *, config: Config, project_root: Path) -> dict[str, Any]:
    try:
        tool = _ALLOWED_TOOLS[name]
    except KeyError as exc:
        raise ValueError(f"Tool is not allowed: {name}") from exc
    return tool(config=config, project_root=project_root)


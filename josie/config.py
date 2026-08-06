"""Minimal local configuration loader without third-party dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    openai_api_key: str | None
    gemini_api_key: str | None
    openai_model: str
    gemini_model: str
    allow_cloud: bool
    log_level: str
    workspace: Path


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config(env_path: Path) -> Config:
    file_values = _read_env_file(env_path)

    def value(name: str, default: str = "") -> str:
        return os.environ.get(name, file_values.get(name, default))

    def boolean(name: str, default: bool = False) -> bool:
        raw = value(name, "true" if default else "false").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    log_level = value("JOSIE_LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        log_level = "INFO"
    return Config(
        openai_api_key=value("OPENAI_API_KEY") or None,
        gemini_api_key=value("GEMINI_API_KEY") or None,
        openai_model=value("OPENAI_MODEL", "gpt-5.6-sol"),
        gemini_model=value("GEMINI_MODEL", "gemini-flash-latest"),
        allow_cloud=boolean("JOSIE_ALLOW_CLOUD"),
        log_level=log_level,
        workspace=Path(value("JOSIE_WORKSPACE", str(env_path.parent))).resolve(),
    )

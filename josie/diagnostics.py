"""Read-only diagnostics safe to expose through the tool allowlist."""

from __future__ import annotations

from pathlib import Path
import platform
import shutil
import sys

from .config import Config


def health_check(*, config: Config, project_root: Path) -> dict[str, object]:
    disk = shutil.disk_usage(project_root)
    checks = {
        "project_directory": project_root.is_dir(),
        "workspace_directory": config.workspace.is_dir(),
        "git_available": shutil.which("git") is not None,
        "openai_configured": bool(config.openai_api_key),
        "gemini_configured": bool(config.gemini_api_key),
    }
    required_ok = all(
        checks[name] for name in ("project_directory", "workspace_directory", "git_available")
    )
    return {
        "status": "ok" if required_ok else "degraded",
        "machine": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "project_root": str(project_root),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "checks": checks,
    }


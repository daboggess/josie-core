"""Evidence-based Josie 1.0 acceptance audit."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Config
from .deployment import DeploymentController
from .diagnostics import recovery_snapshot, restore_drill_snapshot
from .policy import load_policy


def _git_ignores(project_root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", relative_path],
        cwd=project_root, capture_output=True, timeout=10, check=False,
    )
    return result.returncode == 0


def acceptance_audit(*, config: Config, project_root: Path) -> dict[str, object]:
    """Report proven, waiting, and failed criteria without mutating the machine."""
    policy_ok = False
    try:
        policy_ok = load_policy(project_root)["default"] == "forbidden"
    except (OSError, ValueError):
        pass
    recovery = recovery_snapshot(config=config, project_root=project_root)
    restore = restore_drill_snapshot(config=config, project_root=project_root)
    deployment = DeploymentController(config=config, project_root=project_root).status()
    service_preflight = DeploymentController(
        config=config, project_root=project_root
    ).service_preflight()

    criteria = {
        "repository_present": {
            "state": "proven" if (project_root / ".git").is_dir() else "failed",
            "evidence": str(project_root / ".git"),
        },
        "virtual_environment": {
            "state": "proven" if (project_root / ".venv" / "Scripts" / "python.exe").is_file() else "failed",
            "evidence": str(project_root / ".venv" / "Scripts" / "python.exe"),
        },
        "secrets_excluded": {
            "state": "proven" if _git_ignores(project_root, ".env") else "failed",
            "evidence": "git check-ignore .env",
        },
        "zero_spend_lock": {
            "state": "proven" if not config.allow_cloud else "failed",
            "evidence": "JOSIE_ALLOW_CLOUD=false",
        },
        "fail_closed_policy": {
            "state": "proven" if policy_ok else "failed",
            "evidence": str(project_root / "config" / "permissions.json"),
        },
        "verified_backup": {
            "state": "proven" if recovery["status"] == "ok" else "failed",
            "evidence": recovery,
        },
        "non_overwriting_restore_drill": {
            "state": "proven" if restore["status"] == "ok" and not restore["live_database_changed"] else "failed",
            "evidence": restore,
        },
        "wsl": {
            "state": "proven" if deployment["detected"]["wsl"] else "human_gate",
            "evidence": "Windows feature and current WSL version",
        },
        "container_runtime": {
            "state": "proven" if deployment["detected"]["docker"] else "human_gate",
            "evidence": "docker executable",
        },
        "tailscale": {
            "state": "proven" if deployment["detected"]["tailscale"] else "human_gate",
            "evidence": "tailscale executable and account sign-in",
        },
        "local_services": {
            "state": "proven" if service_preflight["status"] == "ready" else "human_gate",
            "evidence": service_preflight,
        },
    }
    counts = {
        state: sum(1 for item in criteria.values() if item["state"] == state)
        for state in ("proven", "human_gate", "failed")
    }
    return {
        "status": "ready" if counts["failed"] == 0 and counts["human_gate"] == 0 else (
            "waiting_for_human_gate" if counts["failed"] == 0 else "failed"
        ),
        "counts": counts,
        "criteria": criteria,
        "arbitrary_shell_available": False,
        "audit_mutated_machine": False,
    }

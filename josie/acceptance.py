"""Evidence-based Josie 1.0 acceptance audit."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Config
from .deployment import DeploymentController
from .diagnostics import recovery_snapshot, restore_drill_snapshot
from .policy import load_policy
from .browser_policy import load_browser_policy


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
    service_runtime = DeploymentController(
        config=config, project_root=project_root
    ).service_runtime_status()
    remote_access = DeploymentController(
        config=config, project_root=project_root
    ).remote_access_status()
    model_lock: dict[str, object] = {}
    try:
        model_lock = __import__("json").loads(
            (project_root / "deploy" / "local-model.lock.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        pass
    firewall = model_lock.get("firewall", {})
    native_model_security_ready = bool(
        model_lock.get("model") == "josie-local:1.0"
        and model_lock.get("cloud_spend_enabled") is False
        and model_lock.get("gpu_enabled") is False
        and isinstance(firewall, dict)
        and firewall.get("lan_allowed") is False
        and firewall.get("tailscale_allowed") is False
    )
    planner_path = project_root / "josie" / "local_model.py"
    planner_text = planner_path.read_text(encoding="utf-8") if planner_path.is_file() else ""
    governed_planner_ready = bool(
        "deterministic_allowlist" in planner_text
        and '"actions_queued": 0' in planner_text
        and '"actions_executed": 0' in planner_text
        and "subprocess" not in planner_text
    )
    workflow_lock_path = project_root / "deploy" / "n8n-workflow.lock.json"
    workflow_lock: dict[str, object] = {}
    try:
        workflow_lock = __import__("json").loads(workflow_lock_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    workflow_validation = workflow_lock.get("validation", {})
    workflow_record = workflow_lock.get("workflow", {})
    storage_guard_ready = bool(
        service_preflight["status"] == "ready"
        and service_runtime.get("storage_monitor", {}).get("ready")
        and isinstance(workflow_record, dict)
        and workflow_record.get("active") is True
        and isinstance(workflow_validation, dict)
        and workflow_validation.get("external_communication") is False
        and workflow_validation.get("executable_node_enabled") is False
        and workflow_validation.get("model_parameters_accepted") is False
    )
    storage_source_path = project_root / "josie" / "storage.py"
    storage_source = storage_source_path.read_text(encoding="utf-8") if storage_source_path.is_file() else ""
    memory_governance_ready = bool(
        "CREATE TABLE IF NOT EXISTS memory_changes" in storage_source
        and '"hard_delete": False' in storage_source
        and "approval_status" in storage_source
    )
    handoff_path = project_root / "josie" / "handoffs.py"
    handoff_source = handoff_path.read_text(encoding="utf-8") if handoff_path.is_file() else ""
    zero_spend_handoffs_ready = bool(
        '"api_budget_cents": 0' in handoff_source
        and '"external_activity": False' in handoff_source
        and '"manual_relay_required": True' in handoff_source
        and "urlopen" not in handoff_source
        and "subprocess" not in handoff_source
        and "CHECK (api_budget_cents = 0)" in storage_source
        and "CHECK (external_activity = 0)" in storage_source
    )
    try:
        browser_policy = load_browser_policy(project_root)
    except (OSError, ValueError, TypeError):
        browser_policy = {}
    browser_policy_ready = bool(
        browser_policy.get("status") == "locked"
        and browser_policy.get("allowed_host_count") == 0
        and browser_policy.get("external_activity") is False
    )

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
            "state": "proven" if deployment["detected"]["tailscale_authenticated"] else "human_gate",
            "evidence": "tailscale executable and account sign-in",
        },
        "local_services": {
            "state": "proven" if service_preflight["status"] == "ready" and service_runtime["status"] == "ready" else "human_gate",
            "evidence": {"preflight": service_preflight, "runtime": service_runtime},
        },
        "local_model": {
            "state": "proven" if service_runtime.get("local_model_ready") else "human_gate",
            "evidence": {
                "model": service_runtime.get("local_model"),
                "ready": service_runtime.get("local_model_ready", False),
                "cloud_calls_allowed": config.allow_cloud,
            },
        },
        "native_model_security": {
            "state": "proven" if native_model_security_ready else "human_gate",
            "evidence": model_lock or "deploy/local-model.lock.json is missing",
        },
        "governed_local_planner": {
            "state": "proven" if governed_planner_ready else "human_gate",
            "evidence": str(planner_path),
        },
        "approval_gated_memory_governance": {
            "state": "proven" if memory_governance_ready else "human_gate",
            "evidence": str(project_root / "josie" / "storage.py"),
        },
        "zero_spend_model_handoffs": {
            "state": "proven" if zero_spend_handoffs_ready else "human_gate",
            "evidence": str(handoff_path),
        },
        "fail_closed_browser_policy": {
            "state": "proven" if browser_policy_ready else "human_gate",
            "evidence": browser_policy or str(project_root / "config" / "browser-policy.json"),
        },
        "storage_headroom_guard": {
            "state": "proven" if storage_guard_ready else "human_gate",
            "evidence": {
                "preflight": service_preflight["status"],
                "monitor": service_runtime.get("storage_monitor"),
                "workflow_lock": workflow_lock or "deploy/n8n-workflow.lock.json is missing",
            },
        },
        "private_remote_access": {
            "state": "proven" if remote_access["status"] == "ready" else "human_gate",
            "evidence": remote_access,
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

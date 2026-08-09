"""Evidence-based Josie 1.0 acceptance audit."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from .config import Config
from .deployment import DeploymentController
from .diagnostics import recovery_snapshot, restore_drill_snapshot
from .policy import load_policy
from .browser_policy import load_browser_policy
from .economic_policy import load_economic_policy


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
    model_grounding = model_lock.get("tool_grounding", {})
    modelfile_path = project_root / "deploy" / "Josie.Modelfile"
    rebuild_script_path = project_root / "scripts" / "Rebuild-JosieLocalModel.ps1"
    modelfile_matches = bool(
        modelfile_path.is_file()
        and model_lock.get("modelfile_sha256")
        == hashlib.sha256(modelfile_path.read_bytes()).hexdigest()
    )
    rebuild_script_matches = bool(
        rebuild_script_path.is_file()
        and model_lock.get("rebuild_script_sha256")
        == hashlib.sha256(rebuild_script_path.read_bytes()).hexdigest()
    )
    native_model_security_ready = bool(
        model_lock.get("model") == "josie-local:1.0"
        and model_lock.get("cloud_spend_enabled") is False
        and model_lock.get("gpu_enabled") is False
        and isinstance(firewall, dict)
        and firewall.get("lan_allowed") is False
        and firewall.get("tailscale_allowed") is False
        and modelfile_matches
        and rebuild_script_matches
        and model_lock.get("rollback_model") == "josie-local:pre-grounding"
        and isinstance(model_grounding, dict)
        and model_grounding.get("expected_tool_call") is True
        and model_grounding.get("grounded_tool_reply") is True
        and model_grounding.get("invented_claims") is False
        and model_grounding.get("cloud_activity") is False
        and model_grounding.get("downloaded_model") is False
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
    try:
        economic_policy = load_economic_policy(project_root)
    except (OSError, ValueError, TypeError):
        economic_policy = {}
    economic_policy_ready = bool(
        economic_policy.get("status") == "locked"
        and economic_policy.get("spending_enabled") is False
        and economic_policy.get("wallet_enabled") is False
        and economic_policy.get("self_modifiable") is False
        and economic_policy.get("transactions_executed") == 0
    )
    proposal_bridge_lock: dict[str, object] = {}
    try:
        proposal_bridge_lock = __import__("json").loads(
            (project_root / "deploy" / "proposal-bridge.lock.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        pass
    bridge_connection = proposal_bridge_lock.get("connection", {})
    bridge_network = proposal_bridge_lock.get("network", {})
    bridge_authority = proposal_bridge_lock.get("authority", {})
    bridge_test = proposal_bridge_lock.get("acceptance_test", {})
    bridge_hashes = proposal_bridge_lock.get("source_sha256", {})
    expected_bridge_sources = {
        "proposal_server": project_root / "deploy" / "proposal-server" / "server.js",
        "compose": project_root / "deploy" / "compose.yaml",
        "activation_script": project_root / "scripts" / "Start-JosieProposalInterface.ps1",
        "status_snapshot_module": project_root / "josie" / "status_snapshot.py",
        "storage_monitor": project_root / "scripts" / "Start-JosieStorageMonitor.ps1",
    }
    bridge_sources_match = bool(
        isinstance(bridge_hashes, dict)
        and all(
            path.is_file()
            and bridge_hashes.get(name)
            == hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in expected_bridge_sources.items()
        )
    )
    openwebui_bridge_ready = bool(
        proposal_bridge_lock.get("status") == "active"
        and isinstance(bridge_connection, dict)
        and bridge_connection.get("id") == "josie-core-review"
        and bridge_connection.get("authentication") == "bearer"
        and bridge_connection.get("enabled") is True
        and bridge_connection.get("secret_in_git") is False
        and isinstance(bridge_network, dict)
        and bridge_network.get("docker_internal") is True
        and bridge_network.get("published_host_port") is False
        and bridge_network.get("internet_listener") is False
        and bridge_network.get("cors_allowed_origins")
        == [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "https://refurb.tail0ab4d2.ts.net",
        ]
        and isinstance(bridge_authority, dict)
        and bridge_authority.get("operation_ids")
        == ["get_josie_status", "record_review_proposal"]
        and bridge_authority.get("actions_executable") is False
        and bridge_authority.get("shell_available") is False
        and bridge_authority.get("cloud_activity_allowed") is False
        and bridge_authority.get("assistant_message_supported") is True
        and bridge_authority.get("status_read_only") is True
        and bridge_authority.get("status_secret_free") is True
        and bridge_authority.get("status_parameters_accepted") is False
        and isinstance(bridge_test, dict)
        and bridge_test.get("proposal_status") == "review_required"
        and bridge_test.get("actions_queued") == 0
        and bridge_test.get("actions_executed") == 0
        and bridge_test.get("cloud_activity") is False
        and bridge_test.get("new_jobs_queued") == 0
        and bridge_test.get("unsupported_shell_kind_http_status") == 400
        and bridge_test.get("cors_allowlist_verified") is True
        and bridge_test.get("untrusted_origin_allowed") is False
        and bridge_test.get("grounded_model_reply_verified") is True
        and bridge_test.get("invented_post_tool_claims") is False
        and bridge_test.get("assistant_message")
        == "No action was performed. A health_check proposal was recorded for human review. Status: review_required. Actions queued: 0. Actions executed: 0."
        and bridge_test.get("duplicate_suppression_verified") is True
        and bridge_test.get("duplicate_retry_same_proposal_id") is True
        and bridge_test.get("duplicate_retry_created_records") == 0
        and bridge_test.get("matching_records_after_two_calls") == 1
        and bridge_test.get("dedupe_window_seconds") == 300
        and bridge_test.get("dedupe_persistence_healthy") is True
        and bridge_test.get("status_http_status") == 200
        and bridge_test.get("status_unauthorized_http_status") == 401
        and bridge_test.get("status_snapshot_fresh") is True
        and bridge_test.get("status_response_allowlisted") is True
        and bridge_test.get("status_proposals_unchanged") is True
        and bridge_test.get("status_jobs_unchanged") is True
        and bridge_test.get("status_actions_queued") == 0
        and bridge_test.get("status_actions_executed") == 0
        and bridge_test.get("status_cloud_activity") is False
        and bridge_sources_match
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
        "zero_dollar_economic_policy": {
            "state": "proven" if economic_policy_ready else "human_gate",
            "evidence": economic_policy or str(project_root / "config" / "economic-policy.json"),
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
        "authenticated_openwebui_status_and_proposal_bridge": {
            "state": "proven" if openwebui_bridge_ready else "human_gate",
            "evidence": proposal_bridge_lock or "deploy/proposal-bridge.lock.json is missing",
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

"""Idempotent deployment controller with explicit human gates."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .diagnostics import external_storage_snapshot, health_check, recovery_snapshot
from .reports import export_diagnostics
from .storage import LocalStore


LOCAL_MODEL = "josie-local:1.0"


def _safe_private_serve(output: str) -> bool:
    lowered = output.lower()
    return bool(
        "tailnet only" in lowered
        and "http://127.0.0.1:3000" in lowered
        and "127.0.0.1:5678" not in lowered
        and "127.0.0.1:3010" not in lowered
        and "funnel on" not in lowered
    )


class DeploymentController:
    def __init__(self, *, config: Config, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self.state_path = project_root / "data" / "deployment-state.json"
        self.manifest_path = project_root / "config" / "deployment.json"

    def _load_state(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {"schema_version": 1, "steps": {}, "updated_at": None}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.state_path)

    def status(self) -> dict[str, object]:
        state = self._load_state()
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        wsl_result = subprocess.run(
            ["wsl.exe", "--status"], capture_output=True, text=True,
            timeout=10, check=False,
        ) if shutil.which("wsl.exe") else None
        local_docker = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"
        tailscale_path = shutil.which("tailscale") or (
            r"C:\Program Files\Tailscale\tailscale.exe"
            if Path(r"C:\Program Files\Tailscale\tailscale.exe").is_file() else None
        )
        tailscale_authenticated = False
        if tailscale_path:
            tailscale_result = subprocess.run(
                [str(tailscale_path), "status", "--json"], capture_output=True, text=True,
                timeout=10, check=False,
            )
            if tailscale_result.returncode == 0:
                try:
                    tailscale_data = json.loads(tailscale_result.stdout)
                    tailscale_authenticated = bool(
                        tailscale_data.get("BackendState") == "Running"
                        and tailscale_data.get("HaveNodeKey")
                        and not tailscale_data.get("AuthURL")
                    )
                except json.JSONDecodeError:
                    pass
        installed = {
            "tailscale": bool(tailscale_path),
            "tailscale_authenticated": tailscale_authenticated,
            "wsl": bool(wsl_result and wsl_result.returncode == 0),
            "docker": bool(shutil.which("docker")) or local_docker.is_file(),
            "node": bool(shutil.which("node")),
            "n8n": bool(shutil.which("n8n")),
        }
        steps = state.get("steps", {})
        if not isinstance(steps, dict):
            steps = {}
        gates = [
            component
            for component in manifest["components"]
            if component["gate"] and steps.get(component["id"]) != "complete"
        ]
        return {
            "status": "ok",
            "state": state,
            "detected": installed,
            "pending_human_gates": gates,
            "cloud_calls_allowed": self.config.allow_cloud,
        }

    def service_runtime_status(self) -> dict[str, object]:
        """Verify local endpoints and the browser execution lock without external traffic."""
        endpoints = {
            "n8n": "http://127.0.0.1:5678/healthz",
            "open_webui": "http://127.0.0.1:3000/health",
            "browser_worker": "http://127.0.0.1:3010/health",
            "ollama": "http://127.0.0.1:11434/api/tags",
        }
        results: dict[str, object] = {}
        for name, url in endpoints.items():
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    body = response.read(4096).decode("utf-8", errors="replace")
                    results[name] = {"ok": response.status == 200, "status_code": response.status, "body": body}
            except Exception as exc:
                results[name] = {"ok": False, "error": type(exc).__name__}
        browser_safe = False
        browser_research_enabled = False
        browser_mode = "unavailable"
        browser = results.get("browser_worker", {})
        if isinstance(browser, dict) and browser.get("ok"):
            try:
                browser_data = json.loads(str(browser.get("body", "{}")))
                locked = (
                    browser_data.get("execution") is False
                    and browser_data.get("allowedHosts") == 0
                )
                read_only = (
                    browser_data.get("execution") is True
                    and browser_data.get("mode") == "read_only_research"
                    and isinstance(browser_data.get("allowedHosts"), int)
                    and browser_data.get("allowedHosts") > 0
                    and browser_data.get("writeActions") is False
                    and browser_data.get("authRequired") is True
                    and browser_data.get("modelDirectAccess") is False
                )
                browser_safe = locked or read_only
                browser_research_enabled = read_only
                browser_mode = "read_only_research" if read_only else "locked" if locked else "unsafe"
            except json.JSONDecodeError:
                pass
        model_ready = False
        ollama = results.get("ollama", {})
        if isinstance(ollama, dict) and ollama.get("ok"):
            try:
                model_data = json.loads(str(ollama.get("body", "{}")))
                model_ready = any(
                    item.get("name") == LOCAL_MODEL
                    for item in model_data.get("models", [])
                    if isinstance(item, dict)
                )
            except json.JSONDecodeError:
                pass
        all_healthy = all(
            isinstance(results[name], dict) and results[name].get("ok")
            for name in endpoints
        )
        storage_monitor: dict[str, object] = {"required": False, "ready": True}
        if self.config.external_storage:
            snapshot_path = self.config.external_storage / "staging" / "storage-status.json"
            storage_monitor = {"required": True, "ready": False, "path": str(snapshot_path)}
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
                created_at = datetime.fromisoformat(str(snapshot["created_at"]))
                age_seconds = max(
                    0, int((datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)).total_seconds())
                )
                monitor_ready = bool(
                    age_seconds <= 900
                    and snapshot.get("status") in {"ok", "warning"}
                    and snapshot.get("cloud_activity") is False
                    and snapshot.get("deletion_performed") is False
                )
                storage_monitor.update(
                    {
                        "ready": monitor_ready,
                        "status": snapshot.get("status"),
                        "age_seconds": age_seconds,
                        "c_free_gb": next(
                            (
                                drive.get("free_gb") for drive in snapshot.get("drives", [])
                                if str(drive.get("drive", "")).upper() == "C:\\"
                            ),
                            None,
                        ),
                    }
                )
            except (OSError, ValueError, KeyError, TypeError):
                storage_monitor["error"] = "storage snapshot missing or invalid"
        return {
            "status": "ready" if all_healthy and browser_safe and model_ready and storage_monitor["ready"] else "waiting",
            "services": results,
            "browser_safe": browser_safe,
            "browser_mode": browser_mode,
            "browser_execution_locked": browser_safe and not browser_research_enabled,
            "browser_research_enabled": browser_research_enabled,
            "browser_write_actions_locked": browser_safe,
            "local_model": LOCAL_MODEL,
            "local_model_ready": model_ready,
            "storage_monitor": storage_monitor,
            "loopback_only": True,
            "cloud_calls_allowed": self.config.allow_cloud,
        }

    def remote_access_status(self) -> dict[str, object]:
        tailscale_path = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
        if not Path(str(tailscale_path)).is_file():
            return {"status": "waiting", "reason": "Tailscale is unavailable"}
        result = subprocess.run(
            [str(tailscale_path), "serve", "status"], capture_output=True, text=True,
            timeout=10, check=False,
        )
        output = result.stdout.strip()
        safe = result.returncode == 0 and _safe_private_serve(output)
        match = re.search(r"https://[^\s]+", output)
        return {
            "status": "ready" if safe else "waiting",
            "tailnet_only": safe,
            "open_webui_only": safe,
            "url": match.group(0) if match else None,
            "public_funnel_enabled": False if safe else None,
        }

    def validate_runtime(self) -> dict[str, object]:
        preflight = self.service_preflight()
        runtime = self.service_runtime_status()
        remote = self.remote_access_status()
        system = self.status()
        ready = bool(
            preflight["status"] == "ready"
            and runtime["status"] == "ready"
            and system["detected"]["wsl"]
            and system["detected"]["docker"]
            and system["detected"]["tailscale_authenticated"]
            and remote["status"] == "ready"
            and not self.config.allow_cloud
        )
        if ready:
            state = self._load_state()
            steps = state.setdefault("steps", {})
            for name in ("tailscale", "wsl", "container_runtime", "n8n", "browser_worker", "open_webui", "local_model"):
                steps[name] = "complete"
            steps["runtime_security"] = {
                "loopback_only": True,
                "browser_execution_locked": True,
                "cloud_spend_lock": True,
                "private_remote_access": True,
            }
            self._save_state(state)
        return {
            "status": "ready" if ready else "waiting",
            "preflight": preflight,
            "runtime": runtime,
            "remote_access": remote,
            "system_detected": system["detected"],
            "state_recorded": ready,
        }

    def service_preflight(self) -> dict[str, object]:
        """Validate staged service controls without downloading or starting anything."""
        deploy_root = self.project_root / "deploy"
        compose_path = deploy_root / "compose.yaml"
        secrets_path = deploy_root / ".env.services"
        issues: list[str] = []

        if not compose_path.is_file():
            issues.append("deploy/compose.yaml is missing")
        else:
            compose = compose_path.read_text(encoding="utf-8")
            forbidden = ("/var/run/docker.sock", "privileged: true", '0.0.0.0:')
            for value in forbidden:
                if value in compose:
                    issues.append(f"forbidden compose setting: {value}")
            for expected in ("127.0.0.1:5678", "127.0.0.1:3000", "127.0.0.1:3010"):
                if expected not in compose:
                    issues.append(f"missing loopback binding: {expected}")
            required_controls = (
                'ENABLE_PERSISTENT_CONFIG: "false"',
                'ENABLE_OLLAMA_API: "true"',
                'OLLAMA_BASE_URL: http://host.docker.internal:11434',
                './open-webui/configure-model.py:/opt/josie/configure-model.py:ro',
                'ENABLE_OPENAI_API: "false"',
                'N8N_BLOCK_ENV_ACCESS_IN_NODE: "true"',
                'N8N_RESTRICT_FILE_ACCESS_TO: /josie-storage/staging',
                'n8n-nodes-base.executeCommand',
                'n8n-nodes-base.localFileTrigger',
                'profiles: ["proposal-interface"]',
                './proposal-server/server.js:/app/server.js:ro',
                '/status:/status:ro',
                '/secrets/proposal-token.txt:/run/secrets/proposal_token:ro',
                'internal: true',
            )
            for value in required_controls:
                if value not in compose:
                    issues.append(f"missing Open WebUI control: {value}")
            if "11434:11434" in compose:
                issues.append("Ollama must not be published by Docker")
            if '- "3030:3030"' in compose or '- "127.0.0.1:3030:3030"' in compose:
                issues.append("Proposal interface must not publish a host port")

        proposal_server_path = deploy_root / "proposal-server" / "server.js"
        if not proposal_server_path.is_file():
            issues.append("bounded proposal server is missing")
        else:
            proposal_server = proposal_server_path.read_text(encoding="utf-8")
            for forbidden_api in ("child_process", "eval(", "exec(", "spawn("):
                if forbidden_api in proposal_server:
                    issues.append(f"proposal server contains forbidden capability: {forbidden_api}")

        workflow_path = deploy_root / "n8n" / "workflows" / "storage-headroom-guard.json"
        if not workflow_path.is_file():
            issues.append("storage headroom workflow is missing")
        else:
            try:
                workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
                node_types = {
                    str(node.get("type")) for node in workflow.get("nodes", [])
                    if isinstance(node, dict)
                }
                if workflow.get("active") is not True:
                    issues.append("storage headroom workflow must be staged active")
                if "n8n-nodes-base.scheduleTrigger" not in node_types:
                    issues.append("storage headroom workflow has no schedule trigger")
                forbidden_nodes = {
                    "n8n-nodes-base.executeCommand",
                    "n8n-nodes-base.ssh",
                    "n8n-nodes-base.httpRequest",
                }
                if node_types & forbidden_nodes:
                    issues.append("storage headroom workflow contains a forbidden node")
            except (OSError, ValueError, TypeError):
                issues.append("storage headroom workflow is invalid JSON")

        images: dict[str, str] = {}
        if not secrets_path.is_file():
            issues.append("deploy/.env.services has not been created after digest verification")
        else:
            for raw_line in secrets_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key in {"N8N_IMAGE", "OPEN_WEBUI_IMAGE", "PLAYWRIGHT_IMAGE"}:
                        images[key] = value
            immutable = re.compile(r"^[^\s]+:[^\s@]+@sha256:[0-9a-fA-F]{64}$")
            for key in ("N8N_IMAGE", "OPEN_WEBUI_IMAGE", "PLAYWRIGHT_IMAGE"):
                if not immutable.fullmatch(images.get(key, "")):
                    issues.append(f"{key} must use a version tag and verified sha256 digest")

        return {
            "status": "ready" if not issues else "waiting",
            "issues": issues,
            "docker_detected": bool(shutil.which("docker")) or (
                Path(os.environ.get("LOCALAPPDATA", ""))
                / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"
            ).is_file(),
            "network_activity": False,
            "services_started": False,
        }

    def run_safe_phase(self) -> dict[str, object]:
        state = self._load_state()
        steps = state.setdefault("steps", {})
        results: dict[str, object] = {}

        external = external_storage_snapshot(config=self.config, project_root=self.project_root)
        results["external_storage"] = external
        steps["external_storage"] = "complete" if external["status"] == "ok" else "waiting"

        store = LocalStore(self.project_root / "data" / "josie.db")
        local_backup = store.create_daily_backup(self.project_root / "data" / "backups")
        external_backup = None
        if self.config.external_storage and self.config.external_storage.is_dir():
            external_backup = store.create_daily_backup(
                self.config.external_storage / "backups" / "josie-database"
            )
        recovery = recovery_snapshot(config=self.config, project_root=self.project_root)
        results["backups"] = {
            "local": str(local_backup),
            "external": str(external_backup) if external_backup else None,
            "integrity": recovery["integrity"],
        }
        steps["local_backups"] = "complete" if recovery["status"] == "ok" else "degraded"

        report = export_diagnostics(config=self.config, project_root=self.project_root)
        results["diagnostics_baseline"] = str(report)
        steps["diagnostics_baseline"] = "complete"
        steps["security_controls"] = {
            "cloud_spend_lock": not self.config.allow_cloud,
            "arbitrary_shell": False,
            "approval_execution": False,
        }
        self._save_state(state)
        return {"status": "ok", "results": results, "state_path": str(self.state_path)}

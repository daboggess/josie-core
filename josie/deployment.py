"""Idempotent deployment controller with explicit human gates."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .config import Config
from .diagnostics import external_storage_snapshot, health_check, recovery_snapshot
from .reports import export_diagnostics
from .storage import LocalStore


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
        installed = {
            "tailscale": bool(shutil.which("tailscale")),
            "wsl": bool(wsl_result and wsl_result.returncode == 0),
            "docker": bool(shutil.which("docker")),
            "node": bool(shutil.which("node")),
            "n8n": bool(shutil.which("n8n")),
        }
        gates = [component for component in manifest["components"] if component["gate"]]
        return {
            "status": "ok",
            "state": state,
            "detected": installed,
            "pending_human_gates": gates,
            "cloud_calls_allowed": self.config.allow_cloud,
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
            "docker_detected": bool(shutil.which("docker")),
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

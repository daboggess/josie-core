"""Publish a strict, secret-free, read-only status snapshot for Josie's UI."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .browser_policy import load_browser_policy
from .config import Config
from .deployment import DeploymentController
from .diagnostics import recovery_snapshot
from .economic_policy import load_economic_policy


MAX_STORAGE_SNAPSHOT_AGE_SECONDS = 900
PROPOSAL_TABLES = ("external_proposals", "model_proposals", "repair_proposals")


def _read_storage_snapshot(config: Config) -> dict[str, object]:
    if config.external_storage is None:
        return {
            "status": "critical",
            "system_free_gb": None,
            "external_free_gb": None,
            "warning_below_gb": 20,
            "critical_below_gb": 15,
            "snapshot_age_seconds": None,
        }
    path = config.external_storage / "staging" / "storage-status.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        created_at = datetime.fromisoformat(str(raw["created_at"]))
        age_seconds = max(
            0,
            int(
                (datetime.now(timezone.utc) - created_at.astimezone(timezone.utc))
                .total_seconds()
            ),
        )
        drives = {
            str(item.get("drive", "")).upper(): item
            for item in raw.get("drives", [])
            if isinstance(item, dict)
        }
        system = drives.get("C:\\", {})
        external = drives.get("D:\\", {})
        status = str(raw.get("status", "critical"))
        valid = bool(
            status in {"ok", "warning", "critical"}
            and age_seconds <= MAX_STORAGE_SNAPSHOT_AGE_SECONDS
            and raw.get("cloud_activity") is False
            and raw.get("deletion_performed") is False
            and isinstance(system.get("free_gb"), (int, float))
            and isinstance(external.get("free_gb"), (int, float))
        )
        return {
            "status": status if valid else "critical",
            "system_free_gb": round(float(system["free_gb"]), 1) if valid else None,
            "external_free_gb": round(float(external["free_gb"]), 1) if valid else None,
            "warning_below_gb": 20,
            "critical_below_gb": 15,
            "snapshot_age_seconds": age_seconds,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {
            "status": "critical",
            "system_free_gb": None,
            "external_free_gb": None,
            "warning_below_gb": 20,
            "critical_below_gb": 15,
            "snapshot_age_seconds": None,
        }


def _pending_proposals(database: Path) -> dict[str, int]:
    counts = {name: 0 for name in PROPOSAL_TABLES}
    if not database.is_file():
        return {"review_required": 0, "external": 0, "model": 0, "repair": 0}
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        for table in PROPOSAL_TABLES:
            if table in existing:
                row = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE status='review_required'"
                ).fetchone()
                counts[table] = int(row[0])
    finally:
        connection.close()
    return {
        "review_required": sum(counts.values()),
        "external": counts["external_proposals"],
        "model": counts["model_proposals"],
        "repair": counts["repair_proposals"],
    }


def _backup_status(config: Config, project_root: Path) -> dict[str, object]:
    recovery = recovery_snapshot(config=config, project_root=project_root)
    latest_name = recovery.get("latest_backup")
    age_hours: float | None = None
    if isinstance(latest_name, str):
        latest_path = project_root / "data" / "backups" / latest_name
        try:
            age_hours = round(
                max(0.0, datetime.now(timezone.utc).timestamp() - latest_path.stat().st_mtime)
                / 3600,
                1,
            )
        except OSError:
            age_hours = None
    raw_integrity = str(recovery.get("integrity", "missing"))
    integrity = "ok" if raw_integrity == "ok" else "missing" if raw_integrity == "missing" else "failed"
    return {
        "status": "ok" if recovery.get("status") == "ok" and integrity == "ok" else "degraded",
        "count": int(recovery.get("backup_count", 0)),
        "latest_age_hours": age_hours,
        "integrity": integrity,
    }


def build_status_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    """Collect local state, then return only the public allowlisted schema."""
    runtime = DeploymentController(config=config, project_root=project_root).service_runtime_status()
    raw_services = runtime.get("services", {})
    services = {
        name: "ok"
        if isinstance(raw_services, dict)
        and isinstance(raw_services.get(name), dict)
        and raw_services[name].get("ok") is True
        else "unavailable"
        for name in ("ollama", "open_webui", "n8n", "browser_worker")
    }
    services["storage_monitor"] = "ok"

    try:
        browser = load_browser_policy(project_root)
        browser_locked = browser.get("status") == "locked" and browser.get("enabled") is False
    except (OSError, ValueError, TypeError):
        browser_locked = False
    try:
        economic = load_economic_policy(project_root)
        spending_locked = bool(
            economic.get("status") == "locked"
            and economic.get("spending_enabled") is False
            and economic.get("wallet_enabled") is False
        )
    except (OSError, ValueError, TypeError):
        spending_locked = False

    storage = _read_storage_snapshot(config)
    backups = _backup_status(config, project_root)
    proposals = _pending_proposals(project_root / "data" / "josie.db")
    safety = {
        "cloud_calls_locked": config.allow_cloud is False,
        "cloud_spending_locked": spending_locked,
        "browser_execution_locked": browser_locked,
        "arbitrary_shell_available": False,
        "actions_executable": False,
    }
    safety_healthy = all((
        safety["cloud_calls_locked"],
        safety["cloud_spending_locked"],
        safety["browser_execution_locked"],
        not safety["arbitrary_shell_available"],
        not safety["actions_executable"],
    ))
    if storage["status"] == "critical" or not safety_healthy:
        overall = "critical"
    elif (
        storage["status"] == "warning"
        or backups["status"] != "ok"
        or any(value != "ok" for value in services.values())
    ):
        overall = "warning"
    else:
        overall = "ok"
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "overall": overall,
        "storage": storage,
        "services": services,
        "backups": backups,
        "proposals": proposals,
        "safety": safety,
        "read_only": True,
        "actions_queued": 0,
        "actions_executed": 0,
        "cloud_activity": False,
    }


def write_status_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    if config.external_storage is None:
        raise RuntimeError("JOSIE_EXTERNAL_STORAGE is required for the status snapshot")
    destination = config.external_storage / "status" / "josie-status.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_status_snapshot(config=config, project_root=project_root)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(destination)
    return snapshot

"""Local diagnostics warnings and secret-free JSON exports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import Config
from .diagnostics import external_storage_snapshot, health_check, recovery_snapshot, storage_snapshot, system_snapshot


def warning_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    system = system_snapshot(config=config, project_root=project_root)
    storage = storage_snapshot(config=config, project_root=project_root)
    recovery = recovery_snapshot(config=config, project_root=project_root)
    external = external_storage_snapshot(config=config, project_root=project_root)
    warnings: list[str] = []
    if system["disk_free_gb"] < 10:
        warnings.append("Disk free space is below 10 GB")
    if system["memory_available_gb"] is not None and system["memory_available_gb"] < 2:
        warnings.append("Available RAM is below 2 GB")
    if storage["status"] != "ok":
        warnings.append("A physical drive is not reporting healthy")
    if recovery["status"] != "ok":
        warnings.append("No verified local recovery backup is available")
    if not external["suitable_drive_present"]:
        warnings.append("Expected 8+ TB external USB drive is not detected")
    return {"status": "warning" if warnings else "ok", "warnings": warnings}


def export_diagnostics(*, config: Config, project_root: Path) -> Path:
    export_dir = project_root / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    destination = export_dir / f"josie-diagnostics-{stamp}.json"
    report = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "health": health_check(config=config, project_root=project_root),
        "system": system_snapshot(config=config, project_root=project_root),
        "storage": storage_snapshot(config=config, project_root=project_root),
        "recovery": recovery_snapshot(config=config, project_root=project_root),
        "external_storage": external_storage_snapshot(config=config, project_root=project_root),
        "warnings": warning_snapshot(config=config, project_root=project_root),
    }
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return destination

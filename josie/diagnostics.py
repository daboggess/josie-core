"""Read-only diagnostics safe to expose through the tool allowlist."""

from __future__ import annotations

from pathlib import Path
import ctypes
import json
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

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


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


def system_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    memory = _MemoryStatus()
    memory.length = ctypes.sizeof(_MemoryStatus)
    memory_ok = bool(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)))
    disk = shutil.disk_usage(project_root)
    return {
        "status": "ok" if memory_ok else "degraded",
        "machine": platform.node(),
        "processor": platform.processor() or "unknown",
        "cpu_logical_count": __import__("os").cpu_count(),
        "memory_total_gb": round(memory.total_physical / (1024**3), 2) if memory_ok else None,
        "memory_available_gb": round(memory.available_physical / (1024**3), 2) if memory_ok else None,
        "memory_load_percent": int(memory.memory_load) if memory_ok else None,
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "cloud_calls_allowed": config.allow_cloud,
    }


def repository_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    del config
    result = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line]
    branch = lines[0] if lines else "unknown"
    changes = lines[1:] if len(lines) > 1 else []
    return {
        "status": "ok" if result.returncode == 0 else "degraded",
        "branch": branch,
        "clean": result.returncode == 0 and not changes,
        "change_count": len(changes),
    }


def uptime_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    del config, project_root
    milliseconds = int(ctypes.windll.kernel32.GetTickCount64())
    total_seconds = milliseconds // 1000
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    return {
        "status": "ok",
        "uptime_seconds": total_seconds,
        "days": days,
        "hours": hours,
        "minutes": minutes,
    }


def storage_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    del config, project_root
    script = (
        "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,HealthStatus,"
        "OperationalStatus,Size | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        return {"status": "degraded", "drives": [], "error": "Windows storage query failed"}
    raw = json.loads(result.stdout or "[]")
    drives = raw if isinstance(raw, list) else [raw]
    normalized = [
        {
            "name": drive.get("FriendlyName", "unknown"),
            "media_type": drive.get("MediaType", "unknown"),
            "health": drive.get("HealthStatus", "unknown"),
            "operational_status": drive.get("OperationalStatus", "unknown"),
            "size_gb": round(int(drive.get("Size", 0)) / (1024**3), 2),
        }
        for drive in drives if drive
    ]
    healthy = bool(normalized) and all(drive["health"] == "Healthy" for drive in normalized)
    return {"status": "ok" if healthy else "degraded", "drives": normalized}


def recovery_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    del config
    backup_dir = project_root / "data" / "backups"
    backups = sorted(backup_dir.glob("josie-*.db"), reverse=True) if backup_dir.exists() else []
    latest = backups[0] if backups else None
    integrity = "missing"
    if latest is not None:
        connection = sqlite3.connect(f"file:{latest}?mode=ro", uri=True)
        try:
            integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            connection.close()
    return {
        "status": "ok" if latest is not None and integrity == "ok" else "degraded",
        "backup_count": len(backups),
        "latest_backup": latest.name if latest else None,
        "integrity": integrity,
    }


def restore_drill_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    """Restore the newest backup into memory and verify it without touching live data."""
    del config
    backup_dir = project_root / "data" / "backups"
    backups = sorted(backup_dir.glob("josie-*.db"), reverse=True)
    if not backups:
        return {"status": "waiting", "reason": "No backup exists", "live_database_changed": False}
    source = sqlite3.connect(f"file:{backups[0]}?mode=ro", uri=True)
    restored = sqlite3.connect(":memory:")
    try:
        source.backup(restored)
        integrity = str(restored.execute("PRAGMA quick_check").fetchone()[0])
        tables = {
            row[0] for row in restored.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"messages", "memories", "tasks", "approvals", "audit", "reminders"}
        counts = {
            table: int(restored.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in sorted(required & tables)
        }
    finally:
        source.close()
        restored.close()
    ready = integrity == "ok" and required.issubset(tables)
    return {
        "status": "ok" if ready else "degraded",
        "backup": backups[0].name,
        "integrity": integrity,
        "required_tables_present": required.issubset(tables),
        "record_counts": counts,
        "live_database_changed": False,
    }


def memory_export_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    """Export governed memory/task records locally; never includes provider secrets."""
    database = project_root / "data" / "josie.db"
    if not database.is_file():
        return {"status": "waiting", "reason": "No Josie database exists"}
    export_root = (
        config.external_storage / "archives" / "memory-exports"
        if config.external_storage and config.external_storage.is_dir()
        else project_root / "data" / "exports"
    )
    export_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    destination = export_root / f"josie-memory-{stamp}.json"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        memory_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(memories)").fetchall()
        }
        memory_fields = ["id", "created_at", "content"]
        memory_fields.extend(field for field in ("updated_at", "status") if field in memory_columns)
        tables = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        data = {
            "schema_version": 2,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": "Josie local database",
            "memories": [dict(row) for row in connection.execute(
                f"SELECT {','.join(memory_fields)} FROM memories ORDER BY id"
            )],
            "tasks": [dict(row) for row in connection.execute(
                "SELECT id,created_at,description,status FROM tasks ORDER BY id"
            )],
            "memory_changes": [dict(row) for row in connection.execute(
                "SELECT id,created_at,memory_id,action,replacement_content,approval_id,status,"
                "applied_at,original_content FROM memory_changes ORDER BY id"
            )] if "memory_changes" in tables else [],
        }
    finally:
        connection.close()
    destination.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "ok",
        "path": str(destination),
        "memory_count": len(data["memories"]),
        "task_count": len(data["tasks"]),
        "cloud_activity": False,
    }


def external_storage_snapshot(*, config: Config, project_root: Path) -> dict[str, object]:
    del project_root
    script = (
        "Get-Disk | Where-Object BusType -eq 'USB' | Select-Object Number,FriendlyName,"
        "PartitionStyle,OperationalStatus,HealthStatus,IsOffline,IsReadOnly,Size | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        return {
            "status": "degraded", "suitable_drive_present": False, "drives": [],
            "configured_path": str(config.external_storage) if config.external_storage else None,
            "configured_path_exists": bool(config.external_storage and config.external_storage.is_dir()),
            "error": "USB disk query failed",
        }
    raw = json.loads(result.stdout or "[]")
    drives = raw if isinstance(raw, list) else [raw]
    normalized = [
        {
            "number": drive.get("Number"),
            "name": drive.get("FriendlyName", "unknown"),
            "partition_style": drive.get("PartitionStyle", "unknown"),
            "operational_status": drive.get("OperationalStatus", "unknown"),
            "health": drive.get("HealthStatus", "unknown"),
            "offline": bool(drive.get("IsOffline", False)),
            "read_only": bool(drive.get("IsReadOnly", False)),
            "size_tb": round(int(drive.get("Size", 0)) / (1024**4), 2),
        }
        for drive in drives if drive
    ]
    suitable = any(drive["size_tb"] >= 8 for drive in normalized)
    configured_exists = bool(config.external_storage and config.external_storage.is_dir())
    return {
        "status": "ok" if suitable and configured_exists else "waiting",
        "suitable_drive_present": suitable,
        "configured_path": str(config.external_storage) if config.external_storage else None,
        "configured_path_exists": configured_exists,
        "drives": normalized,
    }

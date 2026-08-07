"""Read-only diagnostics safe to expose through the tool allowlist."""

from __future__ import annotations

from pathlib import Path
import ctypes
import platform
import shutil
import subprocess
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

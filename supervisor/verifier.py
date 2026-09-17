from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
import time
from pathlib import Path

from .authority import supervised_environment
from .work_order import WorkOrder


PROVEN_RUNTIME_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".cache",
}

PROVEN_RUNTIME_RELATIVE_DIRS = {
    "models",
    "data/private",
    "data/backups",
    ".venv",
    ".harbor-freight-phase0b-temp",
    "tmp",
}

EXCLUDED_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".tmp",
)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_explicitly_allowed(rel_path: str, allowed_paths: tuple[str, ...]) -> bool:
    norm_rel = rel_path.replace("\\", "/").strip("/")
    for allowed in allowed_paths:
        norm_allowed = allowed.replace("\\", "/").strip("/")
        if norm_allowed == norm_rel or norm_allowed.startswith(norm_rel + "/") or norm_rel.startswith(norm_allowed + "/"):
            return True
    return False


def snapshot(workspace: Path, allowed_paths: tuple[str, ...] | list[str] | None = None) -> dict:
    files = {}
    allowed = tuple(allowed_paths or ())
    root_resolved = workspace.resolve()

    for root, dirs, names in os.walk(workspace):
        rel_root = Path(root).resolve().relative_to(root_resolved).as_posix()

        kept_dirs = []
        for d in dirs:
            rel_dir = f"{rel_root}/{d}".lstrip("./") if rel_root != "." else d
            if _is_explicitly_allowed(rel_dir, allowed):
                kept_dirs.append(d)
                continue
            if d in PROVEN_RUNTIME_DIR_NAMES or rel_dir in PROVEN_RUNTIME_RELATIVE_DIRS:
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for name in names:
            if any(name.endswith(suffix) for suffix in EXCLUDED_FILE_SUFFIXES):
                continue
            path = Path(root) / name
            rel = path.relative_to(workspace).as_posix()
            try:
                files[rel] = {"sha256": _hash(path), "size": path.stat().st_size}
            except (FileNotFoundError, PermissionError):
                pass
    git = None
    probe = subprocess.run(["git", "-C", str(workspace), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if probe.returncode == 0:
        head = subprocess.run(["git", "-C", str(workspace), "rev-parse", "HEAD"], capture_output=True, text=True)
        status = subprocess.run(["git", "-C", str(workspace), "status", "--porcelain=v1", "-z", "--", "."], capture_output=True)
        git = {"root": probe.stdout.strip(), "head": head.stdout.strip() if head.returncode == 0 else None, "status_porcelain_hex": status.stdout.hex()}
    return {"files": files, "git": git}


def changed_paths(before: dict, after: dict) -> list[str]:
    keys = set(before["files"]) | set(after["files"])
    return sorted(path for path in keys if before["files"].get(path) != after["files"].get(path))


def attribute_changes(changes: list[str], workspace: Path, supervisor_artifacts: list[Path]) -> tuple[list[str], list[str]]:
    """Separate only exact, pre-registered Supervisor artifacts from worker changes."""
    root = workspace.resolve()
    owned = []
    for artifact in supervisor_artifacts:
        try:
            owned.append(artifact.resolve().relative_to(root).as_posix())
        except ValueError:
            continue
    owned_set = set(owned)
    return sorted(path for path in changes if path not in owned_set), sorted(owned_set)


def _matches(path: str, rules: tuple[str, ...]) -> bool:
    return any(path == rule or path.startswith(rule.rstrip("/") + "/") or fnmatch.fnmatchcase(path, rule) for rule in rules)


def _safe_workspace_path(workspace: Path, relative: str) -> Path:
    target = (workspace / relative).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"acceptance path escapes workspace: {relative}") from exc
    return target


def scope_violations(paths: list[str], order: WorkOrder) -> list[str]:
    return [path for path in paths if not _matches(path, order.allowed_changed_paths) or _matches(path, order.forbidden_paths)]


def run_acceptance(order: WorkOrder, changes: list[str]) -> list[dict]:
    results = []
    for check in order.raw["acceptance"]:
        kind = check["type"]
        start = time.monotonic()
        result = {"type": kind, "passed": False}
        if kind == "file_exists":
            result["passed"] = _safe_workspace_path(order.workspace, check["path"]).is_file()
        elif kind == "file_exact":
            path = _safe_workspace_path(order.workspace, check["path"])
            expected = check.get("content", "").encode(check.get("encoding", "utf-8"))
            result["passed"] = path.is_file() and path.read_bytes() == expected
        elif kind == "command":
            try:
                completed = subprocess.run(check["argv"], cwd=order.workspace, capture_output=True, text=True, timeout=check.get("timeout_seconds", 60), env=supervised_environment())
                result.update({"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "passed": completed.returncode == check.get("expected_exit_code", 0)})
            except subprocess.TimeoutExpired as exc:
                result.update({"exit_code": None, "stdout": exc.stdout or "", "stderr": exc.stderr or "", "timed_out": True, "passed": False})
        elif kind in {"changed_paths", "no_unexpected_files"}:
            violations = scope_violations(changes, order)
            result.update({"violations": violations, "passed": not violations})
        result["elapsed_seconds"] = time.monotonic() - start
        results.append(result)
    return results

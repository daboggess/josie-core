"""Deterministic, local-only software maintenance for Josie.

Maintainer Mode never accepts arbitrary shell text.  Every path, command, Git
transition, test gate, and rollback is enforced here rather than delegated to a
language model.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from .storage import LocalStore


POLICY_PATH = Path("config/maintainer-policy.json")
MAX_REQUEST_CHARS = 8_000
MAX_TEXT_CHARS = 20_000
MAX_OUTPUT_CHARS = 24_000
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
FOCUSED_TEST_PATTERN = re.compile(
    r"tests\.test_josie\.JosieTests\.test_[A-Za-z0-9_]{1,120}"
)
EXPLICIT_REPLACEMENT = re.compile(
    r"(?is)^\s*Maintainer\s+Mode\s*:\s*in\s+([A-Za-z0-9_.\\/-]+)\s*,?\s*"
    r"replace\s+[\"“](.*?)[\"”]\s+with\s+[\"“](.*?)[\"”]"
)
_SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{8,}|"
    r"Bearer\s+[A-Za-z0-9._-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)


class MaintainerError(ValueError):
    """Base class for fail-closed Maintainer Mode errors."""


class PolicyViolation(MaintainerError):
    """The requested operation is outside the deterministic allowlist."""


class ApprovalRequired(MaintainerError):
    """The request touches a protected boundary and must stop for Dustin."""


@dataclass(frozen=True)
class ProcessResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def public(self) -> dict[str, object]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "ok": self.ok,
        }


def _bounded(value: object, *, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise PolicyViolation(f"{label} must be text")
    clean = value.strip()
    if not clean or len(clean) > limit:
        raise PolicyViolation(f"{label} must contain 1 to {limit} characters")
    if _SECRET_VALUE.search(clean):
        raise ApprovalRequired(f"{label} appears to contain a credential or secret")
    return clean


def load_maintainer_policy(project_root: Path) -> dict[str, Any]:
    path = project_root / POLICY_PATH
    if not path.is_file():
        raise PolicyViolation("Maintainer policy is unavailable")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or payload.get("mode") != "maintainer_0_1"
        or payload.get("enabled") is not True
    ):
        raise PolicyViolation("Maintainer policy is invalid or disabled")
    authority = payload.get("authority") or {}
    git = payload.get("git") or {}
    if (
        authority.get("consultants_are_advisory_only") is not True
        or authority.get("consultant_failure_grants_authority") is not False
        or authority.get("self_permission_expansion_allowed") is not False
        or authority.get("package_install_allowed") is not False
        or authority.get("new_container_allowed") is not False
        or authority.get("new_database_allowed") is not False
        or authority.get("network_exposure_change_allowed") is not False
        or git.get("push_allowed") is not False
        or git.get("force_push_allowed") is not False
        or git.get("history_rewrite_allowed") is not False
        or git.get("remove_recovery_tags_allowed") is not False
    ):
        raise PolicyViolation("Maintainer policy weakens a protected boundary")
    return payload


def parse_replacement_request(user_request: str) -> dict[str, str]:
    clean = _bounded(user_request, label="User request", limit=MAX_REQUEST_CHARS)
    match = EXPLICIT_REPLACEMENT.search(clean)
    if match is None:
        raise PolicyViolation(
            'Use: Maintainer Mode: in <path> replace "<exact old text>" '
            'with "<exact new text>".'
        )
    path, old_text, new_text = (item.strip() for item in match.groups())
    if not path or not old_text or not new_text:
        raise PolicyViolation("Maintainer replacement fields may not be empty")
    if len(old_text) > MAX_TEXT_CHARS or len(new_text) > MAX_TEXT_CHARS:
        raise PolicyViolation("Maintainer replacement exceeds the bounded change size")
    if _SECRET_VALUE.search(old_text) or _SECRET_VALUE.search(new_text):
        raise ApprovalRequired("Maintainer text appears to contain a credential or secret")
    return {"path": path.replace("\\", "/"), "old_text": old_text, "new_text": new_text}


def _path_parts(relative: str) -> tuple[str, ...]:
    normalized = relative.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise PolicyViolation("Project path must be relative")
    parts = tuple(item for item in normalized.split("/") if item)
    if any(item in {".", ".."} for item in parts):
        raise PolicyViolation("Path traversal is not allowed")
    return parts


def resolve_project_path(
    project_root: Path, relative: str, *, write: bool = False
) -> tuple[Path, str]:
    policy = load_maintainer_policy(project_root)
    parts = _path_parts(relative)
    normalized = "/".join(parts)
    candidate = (project_root / Path(*parts)).resolve(strict=False)
    root = project_root.resolve()
    if not candidate.is_relative_to(root):
        raise PolicyViolation("Project path escapes the approved root")

    read_policy = policy["read"]
    if parts[0].lower() in {str(item).lower() for item in read_policy["excluded_roots"]}:
        raise ApprovalRequired("The requested path is excluded from Maintainer Mode")
    if candidate.name.lower() in {str(item).lower() for item in read_policy["secret_names"]}:
        raise ApprovalRequired("Credential and environment files are protected")
    if candidate.suffix.lower() in {
        str(item).lower() for item in read_policy["secret_suffixes"]
    }:
        raise ApprovalRequired("Credential and database files are protected")

    current = root
    for part in parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise PolicyViolation("Symbolic-link traversal is not allowed")

    if write:
        write_policy = policy["write"]
        lowered = normalized.lower()
        protected = [str(item).replace("\\", "/").strip("/").lower() for item in write_policy["protected_paths"]]
        if any(lowered == item or lowered.startswith(item + "/") for item in protected):
            raise ApprovalRequired("The requested file is protected and requires Dustin")
        allowed_roots = [
            str(item).replace("\\", "/").strip("/").lower()
            for item in write_policy["allowed_roots"]
        ]
        allowed_files = {str(item).lower() for item in write_policy["allowed_files"]}
        allowed = lowered in allowed_files or any(
            lowered.startswith(item + "/") for item in allowed_roots
        )
        if not allowed:
            raise ApprovalRequired("The requested write path is outside approved development paths")
    return candidate, normalized


def read_file(project_root: Path, relative: str) -> dict[str, object]:
    policy = load_maintainer_policy(project_root)
    path, normalized = resolve_project_path(project_root, relative)
    if not path.is_file():
        raise PolicyViolation("Requested file does not exist")
    size = path.stat().st_size
    if size > int(policy["read"]["max_file_bytes"]):
        raise PolicyViolation("Requested file exceeds the read size limit")
    content = path.read_text(encoding="utf-8")
    if _SECRET_VALUE.search(content):
        raise ApprovalRequired("Requested file appears to contain secret material")
    return {
        "status": "ok",
        "path": normalized,
        "content": content,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "bytes": size,
        "actions_executed": 0,
    }


def search_repo(
    project_root: Path, query: str, *, relative: str = ""
) -> dict[str, object]:
    policy = load_maintainer_policy(project_root)
    clean_query = _bounded(query, label="Search query", limit=200).lower()
    if relative:
        root, normalized_root = resolve_project_path(project_root, relative)
    else:
        root, normalized_root = project_root.resolve(), ""
    if not root.exists():
        raise PolicyViolation("Search root does not exist")
    maximum = int(policy["read"]["max_results"])
    matches: list[dict[str, object]] = []
    paths = [root] if root.is_file() else root.rglob("*")
    for path in paths:
        if len(matches) >= maximum or not path.is_file():
            if len(matches) >= maximum:
                break
            continue
        try:
            relative_name = path.resolve().relative_to(project_root.resolve()).as_posix()
            resolve_project_path(project_root, relative_name)
            if path.stat().st_size > int(policy["read"]["max_file_bytes"]):
                continue
            if clean_query in path.name.lower():
                matches.append({"path": relative_name, "line": 0, "text": path.name})
                continue
            text = path.read_text(encoding="utf-8")
        except (ApprovalRequired, PolicyViolation, OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if clean_query in line.lower():
                matches.append(
                    {"path": relative_name, "line": line_number, "text": line[:500]}
                )
                if len(matches) >= maximum:
                    break
    return {
        "status": "ok",
        "query": query,
        "root": normalized_root,
        "matches": matches,
        "truncated": len(matches) >= maximum,
        "actions_executed": 0,
    }


def _safe_output(value: str) -> str:
    clean = value[-MAX_OUTPUT_CHARS:]
    return _SECRET_VALUE.sub("[credential redacted]", clean)


def _run_process(
    command: list[str], *, cwd: Path, timeout: int
) -> ProcessResult:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
    )
    return ProcessResult(
        command=command,
        returncode=completed.returncode,
        stdout=_safe_output(completed.stdout),
        stderr=_safe_output(completed.stderr),
        duration_seconds=round(time.monotonic() - started, 3),
    )


def _require_ok(result: ProcessResult, label: str) -> ProcessResult:
    if not result.ok:
        detail = result.stderr or result.stdout or f"exit {result.returncode}"
        raise MaintainerError(f"{label} failed: {detail[-800:]}")
    return result


def _git(project_root: Path, arguments: list[str], *, timeout: int = 30) -> ProcessResult:
    return _run_process(["git", *arguments], cwd=project_root, timeout=timeout)


def _command_record(
    kind: str, result: ProcessResult, **extra: object
) -> dict[str, object]:
    return {"kind": kind, **result.public(), **extra}


def git_status(project_root: Path) -> dict[str, object]:
    result = _require_ok(
        _git(project_root, ["status", "--short", "--branch"]), "Git status"
    )
    branch = _require_ok(
        _git(project_root, ["branch", "--show-current"]), "Git branch"
    ).stdout.strip()
    commit = _require_ok(
        _git(project_root, ["rev-parse", "HEAD"]), "Git revision"
    ).stdout.strip()
    return {
        "status": "ok",
        "branch": branch,
        "commit": commit,
        "output": result.stdout,
        "actions_executed": 0,
    }


def git_diff(project_root: Path, relative: str | None = None) -> dict[str, object]:
    arguments = ["diff", "--no-ext-diff"]
    normalized = None
    if relative:
        _, normalized = resolve_project_path(project_root, relative)
        arguments.extend(["--", normalized])
    result = _require_ok(_git(project_root, arguments), "Git diff")
    return {
        "status": "ok",
        "path": normalized,
        "diff": result.stdout,
        "actions_executed": 0,
    }


def run_tests(
    project_root: Path, *, focused_test: str | None = None
) -> dict[str, object]:
    policy = load_maintainer_policy(project_root)
    python = project_root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise PolicyViolation("Josie test interpreter is unavailable")
    if focused_test:
        if FOCUSED_TEST_PATTERN.fullmatch(focused_test) is None:
            raise PolicyViolation("Focused test target is not allowlisted")
        arguments = [str(python), "-m", "unittest", focused_test, "-v"]
        scope = "focused"
    else:
        arguments = [
            str(python),
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-q",
        ]
        scope = "full"
    try:
        result = _run_process(
            arguments,
            cwd=project_root,
            timeout=int(policy["commands"]["full_test_timeout_seconds"]),
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "scope": scope,
            "target": focused_test,
            "command": arguments,
            "returncode": None,
            "output": "Test run timed out",
            "duration_seconds": int(policy["commands"]["full_test_timeout_seconds"]),
        }
    return {
        "status": "passed" if result.ok else "failed",
        "scope": scope,
        "target": focused_test,
        "command": arguments,
        "returncode": result.returncode,
        "output": (result.stdout + "\n" + result.stderr).strip(),
        "duration_seconds": result.duration_seconds,
    }


def run_approved_python(project_root: Path, command_id: str) -> dict[str, object]:
    policy = load_maintainer_policy(project_root)
    commands = {
        "backup_status": ["core.py", "backups", "status"],
        "conversation_status": ["core.py", "conversation", "status"],
    }
    if command_id not in policy["commands"]["python"] or command_id not in commands:
        raise PolicyViolation("Python command is not allowlisted")
    python = project_root / ".venv" / "Scripts" / "python.exe"
    result = _require_ok(
        _run_process(
            [str(python), *commands[command_id]], cwd=project_root, timeout=60
        ),
        "Approved Python command",
    )
    return {"status": "ok", "command_id": command_id, "output": result.stdout}


def run_approved_powershell(project_root: Path, command_id: str) -> dict[str, object]:
    policy = load_maintainer_policy(project_root)
    commands = {
        "service_gate_status": project_root / "scripts" / "Get-JosieGateStatus.ps1"
    }
    if command_id not in policy["commands"]["powershell"] or command_id not in commands:
        raise PolicyViolation("PowerShell command is not allowlisted")
    script = commands[command_id]
    result = _require_ok(
        _run_process(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            cwd=project_root,
            timeout=60,
        ),
        "Approved PowerShell command",
    )
    return {"status": "ok", "command_id": command_id, "output": result.stdout}


def _consultant_records(
    store: LocalStore, request_ids: list[str] | None
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for request_id in (request_ids or [])[:4]:
        if not isinstance(request_id, str) or REQUEST_ID_PATTERN.fullmatch(request_id) is None:
            raise PolicyViolation("Consultant request ID is invalid")
        record = store.subscription_consultation(request_id)
        if record is None:
            raise PolicyViolation("Consultant evidence was not found locally")
        records.append(
            {
                "request_id": request_id,
                "provider": record["provider"],
                "status": record["status"],
            }
        )
    return records


def _event(
    store: LocalStore, job_id: int, event: str, detail: dict[str, object]
) -> None:
    store.add_maintenance_event(job_id=job_id, event=event, detail=detail)
    store.audit("maintenance_" + event, f"job {job_id}")


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.josie-maintenance.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _branch_name(policy: dict[str, Any], normalized: str, request_id: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", Path(normalized).stem.lower()).strip("-")
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:8]
    return f"{policy['git']['branch_prefix']}{stem[:32] or 'change'}-{digest}"


def _assistant_message(record: dict[str, object]) -> str:
    tests = record.get("tests") or {}
    changed = ", ".join(record.get("files_changed") or []) or "none"
    commands = record.get("commands") or []
    lines = [
        "JOSIE MAINTAINER — ACTUAL CONTROL-PLANE RESULT",
        f"Request ID: {record['request_id']}",
        f"Status: {record['status']}",
        f"Approval required: {str(bool(record['approval_required'])).lower()}",
        f"Base checkpoint: {record.get('base_commit') or 'not created'}",
        f"Maintenance branch: {record.get('maintenance_branch') or 'not created'}",
        f"Files changed: {changed}",
        f"Diff summary: {record.get('diff_summary') or 'none'}",
        f"Tests: {tests.get('status', 'not run')}",
        f"Commands recorded: {len(commands)}",
        f"Commit: {record.get('final_commit') or 'none'}",
        f"Rollback: {record.get('rollback_result') or 'not required'}",
    ]
    if record.get("error"):
        lines.append(f"Result detail: {record['error']}")
    lines.append("Remote push performed: false")
    return "\n".join(lines)


def maintenance_public(store: LocalStore, request_id: str) -> dict[str, object] | None:
    record = store.maintenance_job(request_id)
    if record is None:
        return None
    events = store.maintenance_events(int(record["id"]))
    executed_events = {
        "checkpoint_created",
        "file_changed",
        "tests_completed",
        "committed",
        "rolled_back",
        "service_restarted",
    }
    return {
        **record,
        "events": events,
        "assistant_message": _assistant_message(record),
        "local_only": True,
        "arbitrary_shell_available": False,
        "push_performed": False,
        "new_database": False,
        "new_container": False,
        "actions_executed": sum(
            1 for event in events if event.get("event") in executed_events
        ),
    }


def run_text_replacement_job(
    *,
    project_root: Path,
    store: LocalStore,
    request_id: str,
    user_request: str,
    relative_path: str,
    old_text: str,
    new_text: str,
    consultant_request_ids: list[str] | None = None,
    focused_test: str | None = None,
) -> dict[str, object]:
    if REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        raise PolicyViolation("Maintenance request ID is invalid")
    cached = maintenance_public(store, request_id)
    if cached is not None:
        return {**cached, "cached": True}

    clean_request = _bounded(
        user_request, label="User request", limit=MAX_REQUEST_CHARS
    )
    parsed = parse_replacement_request(clean_request)
    normalized_input = relative_path.replace("\\", "/").strip("/")
    if (
        parsed["path"] != normalized_input
        or parsed["old_text"] != old_text
        or parsed["new_text"] != new_text
    ):
        raise PolicyViolation("Tool parameters do not match the explicit user instruction")
    consultants = _consultant_records(store, consultant_request_ids)
    job_id = store.create_maintenance_job(
        request_id=request_id,
        user_request=clean_request,
        operation="replace_text",
        target_path=normalized_input,
        consultants=consultants,
    )
    _event(store, job_id, "requested", {"target_path": normalized_input})

    original_bytes: bytes | None = None
    target: Path | None = None
    base_branch: str | None = None
    commands: list[dict[str, object]] = []
    changed = False
    try:
        policy = load_maintainer_policy(project_root)
        try:
            target, normalized = resolve_project_path(
                project_root, normalized_input, write=True
            )
        except ApprovalRequired as exc:
            store.update_maintenance_job(
                job_id,
                status="approval_required",
                approval_required=True,
                error=str(exc),
            )
            _event(store, job_id, "approval_required", {"reason": str(exc)})
            result = maintenance_public(store, request_id)
            return {**result, "cached": False} if result else {}
        if not target.is_file():
            raise PolicyViolation("Maintainer 0.1 replaces text only in existing files")
        if len(old_text) > int(policy["write"]["max_change_characters"]) or len(
            new_text
        ) > int(policy["write"]["max_change_characters"]):
            raise PolicyViolation("Requested replacement exceeds policy bounds")

        status = _git(project_root, ["status", "--porcelain=v1", "--untracked-files=all"])
        commands.append(_command_record("git_status", status))
        _require_ok(status, "Git status")
        if status.stdout.strip():
            raise PolicyViolation("Working tree must be clean before maintenance")
        branch_result = _git(project_root, ["branch", "--show-current"])
        commands.append(_command_record("git_branch", branch_result))
        base_branch = _require_ok(branch_result, "Git branch").stdout.strip()
        if not base_branch:
            raise PolicyViolation("Maintainer Mode does not operate from detached HEAD")
        revision_result = _git(project_root, ["rev-parse", "HEAD"])
        commands.append(_command_record("git_revision", revision_result))
        base_commit = _require_ok(revision_result, "Git revision").stdout.strip()
        branch = _branch_name(policy, normalized, request_id)
        existing = _git(
            project_root,
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        )
        commands.append(_command_record("git_branch_exists", existing))
        if existing.returncode == 0:
            raise PolicyViolation("Maintenance branch already exists without a matching job")
        switched = _git(project_root, ["switch", "-c", branch])
        commands.append(_command_record("git_switch_checkpoint", switched))
        _require_ok(switched, "Maintenance branch checkpoint")
        store.update_maintenance_job(
            job_id,
            status="in_progress",
            base_branch=base_branch,
            maintenance_branch=branch,
            base_commit=base_commit,
            files_read=[normalized],
            commands=commands,
        )
        _event(
            store,
            job_id,
            "checkpoint_created",
            {"base_branch": base_branch, "base_commit": base_commit, "branch": branch},
        )

        original_bytes = target.read_bytes()
        original_text = original_bytes.decode("utf-8")
        if original_text.count(old_text) != 1:
            raise PolicyViolation("Exact old text must occur once")
        replacement = original_text.replace(old_text, new_text, 1).encode("utf-8")
        _write_bytes_atomic(target, replacement)
        changed = True
        _event(store, job_id, "file_changed", {"path": normalized})

        diff = _require_ok(
            _git(project_root, ["diff", "--no-ext-diff", "--", normalized]),
            "Git diff",
        )
        commands.append(_command_record("git_diff", diff))
        if not diff.stdout.strip():
            raise PolicyViolation("Requested edit produced no Git diff")
        stat_result = _git(project_root, ["diff", "--stat", "--", normalized])
        commands.append(_command_record("git_diff_stat", stat_result))
        stat = _require_ok(stat_result, "Git diff summary").stdout.strip()
        changed_result = _git(project_root, ["diff", "--name-only"])
        commands.append(_command_record("git_changed_paths", changed_result))
        changed_paths = _require_ok(changed_result, "Changed-path check").stdout.splitlines()
        if changed_paths != [normalized]:
            raise PolicyViolation("Maintenance changed a file outside the requested scope")
        store.update_maintenance_job(
            job_id,
            files_changed=[normalized],
            diff_summary=stat,
            commands=commands,
        )
        _event(store, job_id, "diff_recorded", {"summary": stat})

        focused_result = None
        if focused_test:
            focused_result = run_tests(project_root, focused_test=focused_test)
            commands.append(
                {
                    "kind": "focused_tests",
                    "command": focused_result.get("command"),
                    "target": focused_test,
                    "status": focused_result["status"],
                    "returncode": focused_result.get("returncode"),
                }
            )
            if focused_result["status"] != "passed":
                raise MaintainerError("Focused tests failed")
        full_result = run_tests(project_root)
        commands.append(
            {
                "kind": "full_tests",
                "command": full_result.get("command"),
                "status": full_result["status"],
                "returncode": full_result.get("returncode"),
            }
        )
        tests = {"status": full_result["status"], "full": full_result}
        if focused_result is not None:
            tests["focused"] = focused_result
        store.update_maintenance_job(job_id, tests=tests, commands=commands)
        _event(
            store,
            job_id,
            "tests_completed",
            {"status": full_result["status"], "focused": focused_test},
        )
        if full_result["status"] != "passed":
            raise MaintainerError("Full test suite failed")

        after_tests_result = _git(
            project_root, ["status", "--porcelain=v1", "--untracked-files=all"]
        )
        commands.append(_command_record("git_post_test_status", after_tests_result))
        after_tests = _require_ok(after_tests_result, "Post-test status")
        changed_after_tests = [
            line[3:].replace("\\", "/")
            for line in after_tests.stdout.splitlines()
            if len(line) >= 4
        ]
        if changed_after_tests != [normalized]:
            raise PolicyViolation("Tests changed files outside the requested scope")

        added = _git(project_root, ["add", "--", normalized])
        commands.append(_command_record("git_add_scoped", added))
        _require_ok(added, "Scoped Git add")
        staged_check = _git(project_root, ["diff", "--cached", "--check"])
        commands.append(_command_record("git_staged_diff_check", staged_check))
        _require_ok(staged_check, "Staged diff check")
        commit_message = f"Maintainer: update {normalized}"
        committed = _git(project_root, ["commit", "-m", commit_message], timeout=60)
        commands.append(_command_record("git_commit", committed))
        _require_ok(committed, "Maintenance commit")
        committed_revision = _git(project_root, ["rev-parse", "HEAD"])
        commands.append(_command_record("git_committed_revision", committed_revision))
        commit = _require_ok(committed_revision, "Committed revision").stdout.strip()
        store.update_maintenance_job(
            job_id,
            status="completed",
            final_commit=commit,
            commands=commands,
            rollback_result=f"git revert {commit} on {branch}",
        )
        _event(store, job_id, "committed", {"commit": commit, "branch": branch})
    except Exception as exc:
        rollback = "no file change required"
        if changed and target is not None and original_bytes is not None:
            restored_stage = _git(
                project_root, ["restore", "--staged", "--", normalized_input]
            )
            commands.append(_command_record("git_restore_staged", restored_stage))
            _write_bytes_atomic(target, original_bytes)
            rollback = "original bytes restored"
        if base_branch:
            switched_back = _git(project_root, ["switch", base_branch])
            commands.append(_command_record("git_switch_base", switched_back))
            if switched_back.ok:
                rollback += f"; returned to {base_branch}"
        store.update_maintenance_job(
            job_id,
            status="rolled_back" if changed else "blocked",
            commands=commands,
            rollback_result=rollback,
            error=str(exc),
        )
        _event(
            store,
            job_id,
            "rolled_back" if changed else "blocked",
            {"reason": str(exc), "result": rollback},
        )
    result = maintenance_public(store, request_id)
    return {**result, "cached": False} if result else {}


def rollback_maintenance(
    *, project_root: Path, store: LocalStore, request_id: str
) -> dict[str, object]:
    record = store.maintenance_job(request_id)
    if record is None or record.get("status") != "completed":
        raise PolicyViolation("Only a completed maintenance job may be reverted")
    commands = list(record.get("commands") or [])
    status_result = _git(
        project_root, ["status", "--porcelain=v1", "--untracked-files=all"]
    )
    commands.append(_command_record("rollback_git_status", status_result))
    status = _require_ok(status_result, "Git status")
    if status.stdout.strip():
        raise PolicyViolation("Working tree must be clean before rollback")
    branch = str(record.get("maintenance_branch") or "")
    commit = str(record.get("final_commit") or "")
    if not branch or not commit:
        raise PolicyViolation("Maintenance rollback evidence is incomplete")
    current_result = _git(project_root, ["branch", "--show-current"])
    commands.append(_command_record("rollback_git_branch", current_result))
    current = _require_ok(current_result, "Git branch").stdout.strip()
    if current != branch:
        switch_result = _git(project_root, ["switch", branch])
        commands.append(_command_record("rollback_git_switch", switch_result))
        _require_ok(switch_result, "Maintenance branch switch")
    revert_result = _git(
        project_root, ["revert", "--no-edit", commit], timeout=60
    )
    commands.append(_command_record("rollback_git_revert", revert_result))
    reverted = _require_ok(revert_result, "Maintenance revert")
    revision_result = _git(project_root, ["rev-parse", "HEAD"])
    commands.append(_command_record("rollback_git_revision", revision_result))
    revert_commit = _require_ok(revision_result, "Revert revision").stdout.strip()
    store.update_maintenance_job(
        int(record["id"]),
        status="rolled_back",
        commands=commands,
        rollback_result=f"reverted by {revert_commit}",
    )
    _event(
        store,
        int(record["id"]),
        "rolled_back",
        {"original_commit": commit, "revert_commit": revert_commit},
    )
    return {
        "status": "rolled_back",
        "request_id": request_id,
        "original_commit": commit,
        "revert_commit": revert_commit,
        "output": reverted.stdout,
        "history_rewritten": False,
    }


def restart_approved_service(
    *,
    project_root: Path,
    store: LocalStore,
    request_id: str,
    service: str,
    user_request: str,
) -> dict[str, object]:
    if REQUEST_ID_PATTERN.fullmatch(request_id) is None:
        raise PolicyViolation("Maintenance request ID is invalid")
    cached = maintenance_public(store, request_id)
    if cached is not None:
        return {**cached, "cached": True}
    policy = load_maintainer_policy(project_root)
    clean_request = _bounded(
        user_request, label="User request", limit=MAX_REQUEST_CHARS
    )
    expected = re.compile(
        rf"(?im)^\s*Maintainer\s+Mode\s*:\s*restart\s+approved\s+service\s+{re.escape(service)}\s*$"
    )
    if expected.search(clean_request) is None:
        raise PolicyViolation("Service restart requires an exact Maintainer Mode instruction")
    job_id = store.create_maintenance_job(
        request_id=request_id,
        user_request=clean_request,
        operation="restart_service",
        target_path=service,
        consultants=[],
    )
    _event(store, job_id, "requested", {"service": service})
    mapping = policy["commands"]["restart_services"]
    if service not in mapping:
        reason = "Service is not approved for autonomous restart"
        store.update_maintenance_job(
            job_id,
            status="approval_required",
            approval_required=True,
            error=reason,
        )
        _event(store, job_id, "approval_required", {"reason": reason})
        result = maintenance_public(store, request_id)
        return {**result, "cached": False} if result else {}
    commands: list[dict[str, object]] = []
    try:
        status = _git(project_root, ["status", "--porcelain=v1"])
        commands.append(_command_record("git_status", status))
        _require_ok(status, "Git status")
        if status.stdout.strip():
            raise PolicyViolation("Working tree must be clean before restart")
        branch_result = _git(project_root, ["branch", "--show-current"])
        commands.append(_command_record("git_branch", branch_result))
        base_branch = _require_ok(branch_result, "Git branch").stdout.strip()
        revision_result = _git(project_root, ["rev-parse", "HEAD"])
        commands.append(_command_record("git_revision", revision_result))
        base_commit = _require_ok(revision_result, "Git revision").stdout.strip()
        command = [
            "docker",
            "compose",
            "--env-file",
            str(project_root / "deploy" / ".env.services"),
            "-f",
            str(project_root / "deploy" / "compose.yaml"),
            "restart",
            str(mapping[service]),
        ]
        restarted = _run_process(
            command,
            cwd=project_root,
            timeout=int(policy["commands"]["service_restart_timeout_seconds"]),
        )
        commands.append(_command_record("restart_approved_service", restarted))
        _require_ok(restarted, "Approved service restart")
        store.update_maintenance_job(
            job_id,
            status="completed",
            base_branch=base_branch,
            base_commit=base_commit,
            commands=commands,
            diff_summary=f"Restarted approved service {service}; no file diff",
            rollback_result="service restart only; compose restart policy remains unchanged",
        )
        _event(store, job_id, "service_restarted", {"service": service})
    except Exception as exc:
        store.update_maintenance_job(
            job_id,
            status="blocked",
            commands=commands,
            rollback_result="no file or Git state was changed",
            error=str(exc),
        )
        _event(store, job_id, "blocked", {"reason": str(exc)})
    public = maintenance_public(store, request_id)
    return {**public, "cached": False} if public else {}


def maintainer_status(project_root: Path, store: LocalStore) -> dict[str, object]:
    policy = load_maintainer_policy(project_root)
    recent = store.recent_maintenance_jobs(limit=10)
    return {
        "status": "ok",
        "mode": policy["mode"],
        "enabled": True,
        "git": git_status(project_root),
        "write_operations": policy["write"]["operations"],
        "approved_write_roots": policy["write"]["allowed_roots"],
        "protected_paths": policy["write"]["protected_paths"],
        "approved_restart_services": sorted(
            policy["commands"]["restart_services"].keys()
        ),
        "arbitrary_shell_available": False,
        "package_install_allowed": False,
        "push_allowed": False,
        "consultants_are_advisory_only": True,
        "recent_jobs": recent,
        "actions_executed": 0,
    }

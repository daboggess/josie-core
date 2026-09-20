from __future__ import annotations

import json
import os
import re
import shlex
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import VERSION
from .authority import authorize_command
from .priming import (
    PrimingManifest,
    apply_priming_to_work_order,
    assemble_priming_bundle,
)
from .receipts import write_receipt
from .run_job import execute
from .work_order import ValidationError, WorkOrder


ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,95}")
HEADERS = re.compile(r"^(Workspace|Task|Allowed changes|Acceptance|Reporting|Final report):\s*(.*)$", re.I)
ORCHESTRATION = re.compile(
    r"^(?:complete\b|return\b|report\b|do not\b|stop\b|the supervisor\b|"
    r"supervisor\b|fallback\b|use existing\b|treat logs\b)", re.I)
TOKEN = re.compile(r"[a-z0-9][a-z0-9_.\\/-]{2,}", re.I)
STOPWORDS = {
    "and", "are", "for", "from", "into", "must", "not", "only", "that",
    "the", "this", "with", "without", "workspace", "task", "files", "file",
}
ARCH_PATH_PREFIXES = (
    "supervisor/",
    "josie/knowledge.py",
    "josie/context_builder.py",
    "josie/conversation_control.py",
    "mission_manager/",
    "campaign_manager/",
    "docs/architecture/",
)
AUTHORITY_PATH_PREFIXES = (
    "docs/identity/",
    "docs/governance/",
    "josie/authority",
)
OPENCODE = Path(r"I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe")
GOOSE = Path(r"I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe")
GOOSE_CONFIG = Path(r"C:\Users\dusti\AppData\Roaming\Block\goose\config\config.yaml")
CONFIG = Path(r"D:\Josie\config\opencode-local.json")
AGENT_PROFILE = Path(r"D:\Josie\.opencode\agents\josie-coder.md")


def resolve_task_categories(
    task: str = "",
    *,
    prompt_profile: str = "josie-coder-v1",
    allowed_changes: list[str] | None = None,
    retrieval_context: dict | None = None,
) -> tuple[str, ...]:
    """Deterministically resolve relevant canonical knowledge categories for a task.

    Precedence:
    1. Explicit structured "priming_categories" metadata, when valid.
    2. Known route / operation / prompt_profile / task class metadata.
    3. Authorized or allowed changed-path prefixes that deterministically identify a known project area.
    4. Otherwise EMPTY categories.

    Arbitrary conversational wording in `task` alone does NOT trigger categories.
    """
    retrieval = retrieval_context or {}

    # 1. Explicit structured "priming_categories" metadata
    explicit = retrieval.get("priming_categories") or retrieval.get("categories")
    if isinstance(explicit, (list, tuple)):
        valid = tuple(c.strip().lower() for c in explicit if isinstance(c, str) and c.strip())
        if valid:
            return valid

    # 2. Known route / operation / prompt_profile / task class metadata
    task_class = str(retrieval.get("task_class") or retrieval.get("operation") or "").strip().lower()
    if task_class in {"architecture", "supervisor", "supervisor_core"}:
        return ("architecture", "procedure")
    if task_class in {"identity", "governance", "authority"}:
        return ("identity", "procedure")

    # 3. Authorized or allowed changed-path prefixes
    allowed = [p.replace("\\", "/").strip().lstrip("/") for p in (allowed_changes or [])]
    touches_arch = any(
        any(p == prefix.rstrip("/") or p.startswith(prefix) for prefix in ARCH_PATH_PREFIXES)
        for p in allowed
    )
    touches_authority = any(
        any(p == prefix.rstrip("/") or p.startswith(prefix) for prefix in AUTHORITY_PATH_PREFIXES)
        for p in allowed
    )

    categories: list[str] = []
    if touches_arch:
        categories.extend(["architecture", "procedure"])
    if touches_authority:
        if "identity" not in categories:
            categories.append("identity")
        if "procedure" not in categories:
            categories.append("procedure")

    if categories:
        seen = set()
        result = []
        for c in categories:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return tuple(result)

    # 4. Otherwise EMPTY categories
    return ()


class NeedsJobDetails(ValueError):
    pass


def _sections(text: str) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    active = None
    for raw in text.splitlines():
        match = HEADERS.match(raw.strip())
        if match:
            active = match.group(1).lower()
            values[active] = [match.group(2)] if match.group(2) else []
        elif active == "acceptance" and ORCHESTRATION.match(raw.strip()):
            active = "reporting"
            values.setdefault(active, []).append(raw)
        elif active is not None:
            values[active].append(raw)
    required = {"workspace", "task", "allowed changes", "acceptance"}
    missing = sorted(name for name in required if not "\n".join(values.get(name, [])).strip())
    if missing:
        raise NeedsJobDetails("NEEDS_JOB_DETAILS: missing " + ", ".join(missing))
    return {name: "\n".join(lines).strip() for name, lines in values.items()}


def _relevant_evidence(objective: str, evidence: list[dict]) -> list[dict]:
    """Keep only evidence with concrete lexical overlap with the coding task."""
    task_terms = {
        value.lower().strip("._\\/-") for value in TOKEN.findall(objective)
        if value.lower().strip("._\\/-") not in STOPWORDS
    }
    included = []
    for item in evidence[:5]:
        searchable = " ".join(str(item.get(key, "")) for key in (
            "excerpt", "source", "title", "evidence_id"))
        evidence_terms = {
            value.lower().strip("._\\/-") for value in TOKEN.findall(searchable)
            if value.lower().strip("._\\/-") not in STOPWORDS
        }
        if task_terms.intersection(evidence_terms):
            included.append(item)
    return included


def _allowed(text: str) -> list[str]:
    paths = []
    for line in text.splitlines():
        paths.extend(item.strip().lstrip("-* ") for item in line.split(",") if item.strip())
    return paths


def _command_argv(text: str) -> list[str]:
    if "\n" in text.strip():
        raise NeedsJobDetails(
            "NEEDS_JOB_DETAILS: acceptance must contain exactly one command line")
    value = re.sub(r"^command\s*:\s*", "", text.strip(), flags=re.I)
    argv = [item.strip('"') for item in shlex.split(value, posix=False)]
    if not argv:
        raise NeedsJobDetails("NEEDS_JOB_DETAILS: acceptance command is empty")
    decision = authorize_command(value, set())
    if not decision["allowed"]:
        raise NeedsJobDetails("NEEDS_JOB_DETAILS: acceptance command requests denied capability")
    return argv


def parse_remote_job(text: str, *, request_id: str, project_root: Path,
                     retrieval_context: dict | None = None,
                     store: Any = None) -> tuple[dict, Path]:
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError("Invalid local-code job ID")
    sections = _sections(text)
    workspace = Path(sections["workspace"]).resolve()
    if workspace.drive.upper() != "D:" or not workspace.is_dir():
        raise NeedsJobDetails("NEEDS_JOB_DETAILS: workspace must be an existing D: directory")
    private = Path(project_root).resolve() / "data" / "private"
    receipt_dir = private / "supervisor-local-code"
    retrieval = retrieval_context or {}
    candidate_evidence = list(retrieval.get("evidence") or [])[:5]
    evidence = _relevant_evidence(sections["task"], candidate_evidence)
    order = {
        "schema_version": "1",
        "job_id": request_id,
        "objective": sections["task"],
        "first_action": "Inspect the existing source and tests in the workspace.",
        "workspace": str(workspace),
        "harness": "coder",
        "primary_harness_executable": str(GOOSE),
        "fallback_harness_executable": str(OPENCODE),
        "goose_config": str(GOOSE_CONFIG),
        "harness_config": str(CONFIG),
        "agent": "josie-coder",
        "agent_profile": str(AGENT_PROFILE),
        "model": "josie-qual-ornith-1.5-9b-q6",
        "context_limit": 8192,
        "max_tool_repetitions": 3,
        "role": "bounded local coding worker",
        "current_state": f"Operate inside authorized workspace {workspace}; use live files in the authorized workspace as source of truth.",
        "environment": "Windows; local Ollama josie-qual-ornith-1.5-9b-q6; Goose 1.50.0 primary; Goose/OpenCode qwen3:14b fallback.",
        "retrieved_evidence": evidence,
        "retrieval_summary": {
            "performed": bool(retrieval),
            "triggered": bool(retrieval.get("triggered")),
            "reason": str(retrieval.get("reason") or "not_triggered"),
            "knowledge_state": str(retrieval.get("knowledge_state") or "UNKNOWN"),
            "evidence_count": len(evidence),
            "candidate_evidence_count": len(candidate_evidence),
            "packet_chars": len(str(retrieval.get("packet") or "")),
        },
        "prohibited_actions": [
            "access or modify protected canonical memory",
            "install software or download models",
            "use paid or cloud providers",
            "modify files outside the authorized workspace and allowed path list",
        ],
        "reporting_instructions": sections.get("reporting", "") or sections.get("final report", ""),
        "fallback_conditions": [
            "runtime failure", "timeout or no tool activity", "verification loop",
            "invalid tool execution", "acceptance failure after repair", "worker blocker",
        ],
        "side_effect_capabilities": [],
        "requires_modification": True,
        "allowed_changed_paths": _allowed(sections["allowed changes"]),
        "timeout_seconds": 360,
        "stall_seconds": 180,
        "max_attempts": 2,
        "acceptance": [
            {"type": "command", "argv": _command_argv(sections["acceptance"]), "expected_exit_code": 0, "timeout_seconds": 60},
            {"type": "changed_paths"},
            {"type": "no_unexpected_files"},
        ],
        "prompt_profile": "josie-coder-v1",
        "receipt_destination": str(receipt_dir),
        "ollama_url": "http://127.0.0.1:11434",
    }

    # Resolve store if not explicitly passed
    active_store = store
    if active_store is None:
        db_path = Path(project_root).resolve() / "data" / "josie.db"
        if db_path.is_file():
            from josie.storage import LocalStore
            active_store = LocalStore(db_path)

    # Deterministic Priming Integration:
    # Supplements existing retrieval with bounded canonical knowledge excerpts
    categories = resolve_task_categories(
        sections["task"],
        prompt_profile="josie-coder-v1",
        allowed_changes=order["allowed_changed_paths"],
        retrieval_context=retrieval,
    )

    try:
        if categories:
            from josie.knowledge import assemble_priming_from_knowledge
            manifest = PrimingManifest(
                task_id=request_id,
                knowledge_categories=categories,
            )
            bundle = assemble_priming_from_knowledge(
                manifest,
                store=active_store,
                include_superseded=False,
                include_rejected=False,
            )
        else:
            manifest = PrimingManifest(task_id=request_id)
            bundle = assemble_priming_bundle(manifest, [])
    except Exception:
        manifest = PrimingManifest(task_id=request_id)
        bundle = assemble_priming_bundle(manifest, [])

    apply_priming_to_work_order(order, bundle)
    WorkOrder.validate(order)
    order_dir = private / "supervisor-work-orders"
    order_dir.mkdir(parents=True, exist_ok=True)
    order_path = order_dir / f"{request_id}.json"
    if order_path.exists():
        raise ValueError("Job ID already exists")
    temporary = order_path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(order, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, order_path)
    return order, order_path


def _public(request_id: str, receipt: dict, receipt_path: Path) -> dict:
    status = receipt.get("final_status", "ERROR")
    reason = receipt.get("reason", "UNKNOWN")
    acceptance = receipt.get("acceptance_results") or []
    accepted = bool(acceptance) and all(item.get("passed") is True for item in acceptance)
    changed = receipt.get("changed_files") or []
    rid = receipt.get("receipt_id", receipt_path.stem)
    result_label = "PASS" if status == "PASS" else reason
    message = "\n".join((
        "JOSIE LOCAL CODE — ACTUAL RESULT",
        f"LOCAL CODE RESULT: {result_label}",
        f"Job: {request_id}",
        f"Changed: {', '.join(changed) or 'none'}",
        f"Acceptance: {'PASS' if accepted else 'FAIL'}",
        f"Elapsed: {receipt.get('elapsed_seconds', 0):.3f} seconds",
        f"Receipt: {rid}",
        f"Harness: {receipt.get('selected_harness') or receipt.get('harness', 'not run')}",
        f"Fallback: {'YES' if receipt.get('fallback_occurred') else 'NO'}",
        f"Reason: {reason}",
    ))
    return {"request_id": request_id, "status": status.lower(), "reason": reason,
            "changed_files": changed, "receipt": str(receipt_path), "receipt_id": rid,
            "assistant_message": message}


def _receipt_for_job(receipt_dir: Path, request_id: str) -> tuple[dict, Path] | None:
    for path in sorted(receipt_dir.glob("*.json"), key=lambda item: item.stat().st_mtime,
                       reverse=True):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("job_id") == request_id:
            return receipt, path
    return None


def _accepted(request_id: str, order_path: Path) -> dict:
    message = "\n".join((
        "JOSIE LOCAL CODE — ACTUAL RESULT",
        "LOCAL CODE RESULT: ACCEPTED",
        f"Job: {request_id}",
        "Worker launch: not yet evidenced",
        f"Work order: {order_path}",
    ))
    return {"request_id": request_id, "status": "accepted", "reason": "ACCEPTED",
            "work_order": str(order_path), "assistant_message": message}


def _record_failure(project_root: Path, request_id: str, *, reason: str,
                    error: Exception, final_status: str = "BLOCKED",
                    worker_launched: bool | None = False) -> tuple[dict, Path]:
    receipt_dir = project_root.resolve() / "data" / "private" / "supervisor-local-code"
    recorded_at = datetime.now(timezone.utc).isoformat()
    receipt = {
        "schema_version": "1",
        "supervisor_version": VERSION,
        "job_id": request_id,
        "started_at": recorded_at,
        "ended_at": recorded_at,
        "elapsed_seconds": 0,
        "harness": "coder",
        "harness_version": "NOT_RUN" if worker_launched is False else "UNKNOWN",
        "requested_model": "josie-qual-ornith-1.5-9b-q6",
        "worker_launched": worker_launched,
        "final_status": final_status,
        "reason": reason,
        "error_type": type(error).__name__,
        "error": str(error),
        "traceback": traceback.format_exc(),
        "acceptance_results": [],
        "changed_files": [],
        "tool_activity": [],
    }
    path = write_receipt(receipt_dir, receipt)
    return json.loads(path.read_text(encoding="utf-8")), path


def delegate_supervised_local_code(task, acceptance_criteria, *, request_id, project_root,
                                   retrieval_context=None, store=None):
    del acceptance_criteria
    root = Path(project_root).resolve()
    receipt_dir = root / "data" / "private" / "supervisor-local-code"
    existing = _receipt_for_job(receipt_dir, request_id)
    if existing is not None:
        return _public(request_id, *existing)
    order_path = root / "data" / "private" / "supervisor-work-orders" / f"{request_id}.json"
    if order_path.is_file():
        return _accepted(request_id, order_path)
    try:
        _, order_path = parse_remote_job(
            task, request_id=request_id, project_root=root,
            retrieval_context=retrieval_context,
            store=store)
    except NeedsJobDetails as exc:
        receipt, receipt_path = _record_failure(
            root, request_id, reason="NEEDS_JOB_DETAILS", error=exc)
        return _public(request_id, receipt, receipt_path)
    except (ValidationError, ValueError) as exc:
        receipt, receipt_path = _record_failure(
            root, request_id, reason="VALIDATION_FAIL", error=exc)
        return _public(request_id, receipt, receipt_path)
    try:
        receipt, receipt_path = execute(order_path)
    except Exception as exc:
        receipt, receipt_path = _record_failure(
            root, request_id, reason="SUPERVISOR_ERROR", error=exc,
            final_status="FAIL", worker_launched=None)
        return _public(request_id, receipt, receipt_path)
    if receipt_path is None or not receipt_path.is_file():
        exc = RuntimeError("Supervisor did not produce an authoritative receipt")
        receipt, receipt_path = _record_failure(
            root, request_id, reason="SUPERVISOR_NO_RECEIPT", error=exc,
            final_status="FAIL", worker_launched=None)
        return _public(request_id, receipt, receipt_path)
    authoritative = json.loads(receipt_path.read_text(encoding="utf-8"))
    return _public(request_id, authoritative, receipt_path)


def supervised_local_code_status(root, request_id):
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError("Invalid local-code job ID")
    receipt_dir = Path(root).resolve() / "data" / "private" / "supervisor-local-code"
    existing = _receipt_for_job(receipt_dir, request_id)
    if existing is not None:
        return _public(request_id, *existing)
    order_path = (Path(root).resolve() / "data" / "private" /
                  "supervisor-work-orders" / f"{request_id}.json")
    if order_path.is_file():
        return _accepted(request_id, order_path)
    return {"request_id": request_id, "status": "not_found",
            "assistant_message": "JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: NOT_FOUND\nJob: " + request_id}

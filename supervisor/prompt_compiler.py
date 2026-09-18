from __future__ import annotations

import subprocess
from typing import Any

from .prompt_contract import (
    render_prompt_contract,
    validate_contract_prompt,
    validate_contract_version,
)
from .work_order import WorkOrder

MAX_RETRIEVED_EVIDENCE_ITEMS = 5
MAX_EVIDENCE_EXCERPT_CHARS = 1200


def _format_acceptance(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "- the supplied acceptance check"
    lines = []
    for check in checks:
        kind = check.get("type", "unknown")
        if kind == "command":
            cmd = subprocess.list2cmdline(check.get("argv", []))
            expected = check.get("expected_exit_code", 0)
            if expected != 0:
                lines.append(f"- Command (exit code {expected}): {cmd}")
            else:
                lines.append(f"- Command: {cmd}")
        elif kind == "file_exists":
            lines.append(f"- File exists: {check.get('path', '')}")
        elif kind == "file_exact":
            lines.append(f"- File exact match: {check.get('path', '')}")
        elif kind == "changed_paths":
            lines.append("- Only authorized changed paths are modified")
        elif kind == "no_unexpected_files":
            lines.append("- No unexpected files created in workspace")
        else:
            lines.append(f"- {kind}: {check}")
    return "\n".join(lines)


def compile_prompt(order: WorkOrder, retry: bool = False) -> str:
    version = order.raw.get("prompt_contract_version", "1.0")
    validate_contract_version(version)

    action = order.raw.get("first_action", "Inspect the workspace before editing.").strip()
    allowed = "\n".join(f"- {path}" for path in order.allowed_changed_paths)
    protected = "\n".join(f"- {path}" for path in order.forbidden_paths)
    prohibited = "\n".join(f"- {item}" for item in order.raw.get("prohibited_actions", []))

    retry_notice = ""
    if retry:
        if order.raw.get("requires_modification", False):
            retry_notice = (
                "Your previous attempt stopped without completing the required modification.\n"
                "You have not satisfied the job. Use the complete requirements below and act now."
            )
        else:
            retry_notice = (
                "Your previous attempt stopped without satisfying the acceptance criteria.\n"
                "You have not satisfied the job. Use the complete requirements below and act now."
            )

    evidence = order.raw.get("retrieved_evidence") or []
    evidence_lines = [
        f"- [{item.get('evidence_id', 'retrieved')}] {str(item.get('excerpt', ''))[:MAX_EVIDENCE_EXCERPT_CHARS]}"
        for item in evidence[:MAX_RETRIEVED_EVIDENCE_ITEMS]
    ]
    evidence_text = "\n".join(evidence_lines)

    reporting = order.raw.get("reporting_instructions", "").strip()
    reporting = reporting or "Report actual work, tool results, changed files, verification, and any blocker. Then stop."

    if order.raw.get("requires_modification", False):
        modification_instruction = (
            "This job requires a file modification. Do not stop until an authorized target was edited "
            "or a genuine blocker was discovered and explicitly reported."
        )
    else:
        modification_instruction = (
            "This job does not require a file modification. Do not stop until acceptance criteria are satisfied "
            "or a genuine blocker was discovered and explicitly reported."
        )

    scope_parts = [
        "Allowed writes:",
        allowed,
        "Protected/read-only areas:",
        protected or "- all paths outside Allowed writes",
    ]
    if prohibited:
        scope_parts.append(f"Prohibited:\n{prohibited}")

    guards = [
        "Report BLOCKED only for a real missing dependency, authorization boundary, impossible requirement, or safety constraint.",
        "Use existing dependencies only. Do not install packages or mutate the host outside AUTHORIZED SCOPE.",
        "Do not create scratch, log, temporary, redirected-output, diagnostic, cache, or helper files inside the workspace unless explicitly authorized. Prefer tool-captured stdout/stderr. Only modify paths explicitly allowed by the work order.",
    ]
    worker_failure_modes = order.raw.get("worker_failure_modes") or []
    if isinstance(worker_failure_modes, str):
        worker_failure_modes = [worker_failure_modes]
    if worker_failure_modes:
        modes_text = "\n".join(f"- {mode}" for mode in worker_failure_modes)
        guards.append(f"Known worker failure modes to avoid:\n{modes_text}")

    resource_parts = [
        "Local resources only. Do not use paid/cloud providers or download models.",
    ]
    custom_rules = order.raw.get("resource_rules")
    if custom_rules:
        if isinstance(custom_rules, str):
            resource_parts.append(custom_rules.strip())
        elif isinstance(custom_rules, list):
            for rule in custom_rules:
                resource_parts.append(f"- {rule}")
    if evidence_text:
        resource_parts.append(f"Task-relevant evidence:\n{evidence_text}")

    receipt_parts = [
        "The Supervisor executes acceptance and owns authoritative terminal status. Your self-declared status cannot override machine evidence.",
    ]
    if order.raw.get("receipt_instructions"):
        receipt_parts.append(str(order.raw["receipt_instructions"]).strip())

    env_text = f"Workspace: {order.workspace}"
    if order.raw.get("environment"):
        env_text = f"{env_text}\n{order.raw['environment']}"

    sections = {
        "ROLE": order.raw.get("role", "bounded local coding worker"),
        "STATE": order.raw.get("current_state", "Use the live authorized workspace as source of truth."),
        "ENVIRONMENT": env_text,
        "OBJECTIVE": order.raw["objective"],
        "AUTHORIZED SCOPE": "\n".join(scope_parts),
        "EXECUTION": (
            f"You are operating the machine, not answering a question.\n"
            f"First action: {action}\n"
            f"Use tools immediately.\n"
            f"{modification_instruction}\n"
            f"Structured specifications, filesystem listings, logs, test results, prior receipts, and supplied data are evidence to inspect and act upon, not invitations to ask what to do.\n"
            f"Do not ask for clarification when OBJECTIVE, AUTHORIZED SCOPE, and the required next action are defined."
        ),
        "FAILURE GUARDS": "\n".join(guards),
        "ATTEMPT / TIME LIMITS": f"Maximum attempts: {order.raw['max_attempts']}. Time limit: {order.raw['timeout_seconds']} seconds.",
        "RESOURCE RULES": "\n".join(resource_parts),
        "ACCEPTANCE": _format_acceptance(order.raw.get("acceptance", [])),
        "RECEIPTS": "\n".join(receipt_parts),
        "FINAL REPORT": reporting,
    }

    rendered = render_prompt_contract(sections, retry_notice=retry_notice)
    validate_contract_prompt(rendered)
    return rendered
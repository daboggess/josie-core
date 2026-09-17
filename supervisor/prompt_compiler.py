import subprocess

from .work_order import WorkOrder


def compile_prompt(order: WorkOrder, retry: bool = False) -> str:
    action = order.raw.get("first_action", "Inspect the workspace before editing.")
    allowed = "\n".join(f"- {path}" for path in order.allowed_changed_paths)
    acceptance = next((subprocess.list2cmdline(check["argv"]) for check in order.raw["acceptance"] if check["type"] == "command"), "the supplied acceptance check")
    retry_notice = ""
    if retry:
        retry_notice = """Your previous attempt stopped without completing the required modification.
You have not satisfied the job. Use the complete requirements below and act now.

"""
    evidence = order.raw.get("retrieved_evidence") or []
    evidence_text = "\n".join(
        f"- [{item.get('evidence_id', 'retrieved')}] {str(item.get('excerpt', ''))[:1200]}"
        for item in evidence[:5]
    ) or "- none; inspect only the authorized workspace"
    reporting = order.raw.get("reporting_instructions", "").strip()
    reporting = reporting or "Report actual work, tool results, changed files, verification, and any blocker. Then stop."
    protected = "\n".join(f"- {path}" for path in order.forbidden_paths)
    prohibited = "\n".join(f"- {item}" for item in order.raw.get("prohibited_actions", []))
    return f"""{retry_notice}ROLE
{order.raw.get('role', 'bounded local coding worker')}

STATE
{order.raw.get('current_state', 'Use the live authorized workspace as source of truth.')}

ENVIRONMENT
Workspace: {order.workspace}
{order.raw.get('environment', '')}

OBJECTIVE
{order.raw['objective']}

AUTHORIZED SCOPE
Allowed writes:
{allowed}
Protected/read-only areas:
{protected or '- all paths outside Allowed writes'}
{('Prohibited:\n' + prohibited) if prohibited else ''}

EXECUTION
You are operating the machine, not answering a question.
First action: {action}
Use tools immediately.
This job requires a file modification. Do not stop until an authorized target was edited or a genuine blocker was discovered and explicitly reported.
Structured specifications, filesystem listings, logs, test results, prior receipts, and supplied data are evidence to inspect and act upon, not invitations to ask what to do.
Do not ask for clarification when OBJECTIVE, AUTHORIZED SCOPE, and the required next action are defined.

FAILURE GUARDS
Report BLOCKED only for a real missing dependency, authorization boundary, impossible requirement, or safety constraint.
Use existing dependencies only. Do not install packages or mutate the host outside AUTHORIZED SCOPE.
Do not create scratch, log, temporary, redirected-output, diagnostic, cache, or helper files inside the workspace unless explicitly authorized. Prefer tool-captured stdout/stderr. Only modify paths explicitly allowed by the work order.

ATTEMPT / TIME LIMITS
Maximum attempts: {order.raw['max_attempts']}. Time limit: {order.raw['timeout_seconds']} seconds.

RESOURCE RULES
Local resources only. Do not use paid/cloud providers or download models.
{('Task-relevant evidence:\n' + evidence_text) if evidence else ''}

ACCEPTANCE
{acceptance}

RECEIPTS
The Supervisor executes acceptance and owns authoritative terminal status. Your self-declared status cannot override machine evidence.

FINAL REPORT
{reporting}"""

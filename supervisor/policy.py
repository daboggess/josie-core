TERMINAL = {"PASS", "FAIL", "BLOCKED", "ERROR"}

# Hard blockers: environment/system failures where fallback/retry cannot succeed without external intervention.
HARD_EXTERNAL_BLOCKERS = {
    "PREFLIGHT_BLOCKED",
    "PREFLIGHT_MISSING_RUNTIME",
    "PREFLIGHT_MISSING_MODEL",
    "THERMAL_PREFLIGHT_BLOCKED",
    "SUPERVISOR_FAILURE",
    "WORKSPACE_UNAVAILABLE",
    "DENIED_ACTION",
    "DEPENDENCY_DEADLOCK",
}

# Recoverable worker failures: failures caused by worker-local reasoning, tool-formulation, test, or self-reporting issues.
RECOVERABLE_WORKER_FAILURES = {
    "WORKER_BLOCKED",
    "FAIL_ACCEPTANCE",
    "FAIL_SCOPE",
    "PREMATURE_STOP",
    "FAIL_WORKER",
    "FAIL_TIMEOUT",
    "FAIL_TOOL_EXECUTION",
    "FAIL_NO_TOOL_ACTIVITY",
    "FAIL_STALL",
    "CONTEXT_EXCEEDED",
    "PROCESS_TIMEOUT",
    "NONZERO_EXIT",
    "TOOL_CALL_PARSE_FAILED",
    "EMPTY_OUTPUT",
    "HARNESS_ERROR",
    "HARNESS_STEP_LIMIT",
}

FALLBACK_REASONS = {
    "CONTEXT_EXCEEDED", "PROCESS_TIMEOUT", "FAIL_TIMEOUT",
    "NONZERO_EXIT", "FAIL_WORKER", "TOOL_CALL_PARSE_FAILED",
    "FAIL_TOOL_EXECUTION", "EMPTY_OUTPUT", "FAIL_NO_TOOL_ACTIVITY",
    "PREMATURE_STOP", "HARNESS_ERROR", "FAIL_STALL", "LAUNCH_ERROR",
    "UNEXPECTED_EXCEPTION", "SUPERVISOR_ERROR",
    "WORKER_BLOCKED", "FAIL_ACCEPTANCE", "FAIL_SCOPE",
    "HARNESS_STEP_LIMIT",
}


def is_hard_blocker(reason: str) -> bool:
    return reason in HARD_EXTERNAL_BLOCKERS


def is_recoverable_worker_failure(reason: str) -> bool:
    return reason in RECOVERABLE_WORKER_FAILURES


def decide(*, launched: bool, preflight_ok: bool, timed_out: bool, exit_code: int | None, violations: list[str], acceptance: list[dict]) -> tuple[str, str]:
    if not preflight_ok:
        return "BLOCKED", "PREFLIGHT_BLOCKED"
    if not launched:
        return "FAIL", "NOT_RUN"
    if timed_out:
        return "FAIL", "FAIL_TIMEOUT"
    if exit_code != 0:
        return "FAIL", "FAIL_WORKER"
    if violations:
        return "FAIL", "FAIL_SCOPE"
    if not acceptance or not all(item.get("passed") is True for item in acceptance):
        return "FAIL", "FAIL_ACCEPTANCE"
    return "PASS", "PASS"


def classify_premature_stop(*, requires_modification: bool, exit_code: int | None,
                            timed_out: bool, violations: list[str], changes: list[str],
                            acceptance: list[dict], tool_names: list[str],
                            blocker_reported: bool, denied_actions: list[dict]) -> bool:
    inspection = {"glob", "read", "grep", "list"}
    unsafe_succeeded = any(not item.get("prevented_before_execution", False) for item in denied_actions)
    return bool(
        requires_modification and exit_code == 0 and not timed_out and not violations
        and not changes and acceptance and not all(item.get("passed") is True for item in acceptance)
        and set(tool_names) <= inspection and not blocker_reported and not unsafe_succeeded
    )


def should_retry(reason: str, attempt: int, max_attempts: int) -> bool:
    return reason in {
        "PREMATURE_STOP", "FAIL_ACCEPTANCE", "FAIL_TOOL_EXECUTION",
        "FAIL_NO_TOOL_ACTIVITY", "HARNESS_STEP_LIMIT",
    } and attempt < max_attempts


def should_fallback(reason: str) -> bool:
    if is_hard_blocker(reason):
        return False
    return reason in FALLBACK_REASONS or is_recoverable_worker_failure(reason)


def model_race_verdict(candidates: list[dict], baseline: str) -> str:
    winners = [row for row in candidates if row.get("status") == "PASS" and row.get("required_evidence") is True and row.get("beats_baseline") is True]
    if len(winners) > 1:
        raise ValueError("contradictory result data: multiple winners")
    if winners:
        return winners[0]["name"]
    if any(row.get("declared_winner") and row.get("status") in {"NOT_RUN", "BLOCKED", "INCOMPATIBLE", "TOOL_GATE_FAIL"} for row in candidates):
        raise ValueError("impossible winner state")
    return baseline


# Conceptual escalation order for Josie:
# 1. deterministic/local non-LLM execution when sufficient
# 2. primary local coding worker
# 3. local fallback/reviewer when appropriate
# 4. Antigravity Flash
# 5. Antigravity Pro
# 6. existing Codex escalation
# 7. paid API only when explicitly authorized by policy/user
ESCALATION_LADDER: list[str] = [
    "deterministic_local",
    "primary_local_worker",
    "local_fallback_reviewer",
    "antigravity_flash",
    "antigravity_pro",
    "codex",
    "paid_api_authorized",
]

TIER_DESCRIPTIONS: dict[str, str] = {
    "deterministic_local": "Deterministic / local non-LLM execution when sufficient",
    "primary_local_worker": "Primary local coding worker (Goose with josie-qual-ornith-1.5-9b-q6)",
    "local_fallback_reviewer": "Local fallback / reviewer when appropriate (Goose/OpenCode with qwen3:14b)",
    "antigravity_flash": "Antigravity Flash (Gemini 3.8 Flash High via agy)",
    "antigravity_pro": "Antigravity Pro (Gemini 3.1 Pro High via agy)",
    "codex": "Existing Codex escalation (ChatGPT-authenticated CLI)",
    "paid_api_authorized": "Paid API only when explicitly authorized by policy/user",
}


def next_escalation_tier(
    current_tier: str | None,
    *,
    task_requires_stronger_reasoning: bool = False,
    antigravity_flash_available: bool = True,
    antigravity_flash_quota_exhausted: bool = False,
    antigravity_pro_available: bool = True,
    antigravity_pro_quota_exhausted: bool = False,
    codex_available: bool = True,
    paid_authorized: bool = False,
) -> tuple[str | None, dict]:
    """Determine the next resource tier in the authoritative Josie escalation ladder.

    Order:
    1. deterministic_local
    2. primary_local_worker
    3. local_fallback_reviewer
    4. antigravity_flash
    5. antigravity_pro
    6. codex
    7. paid_api_authorized (only when explicitly authorized)

    If Antigravity quota is exhausted or unavailable, records that state and continues
    to the next authorized escalation rather than failing the whole job.
    Paid API fallback is NEVER silently used.
    """
    audit = {
        "from_tier": current_tier,
        "paid_ai_credits": "OFF",
        "paid_api_authorized": paid_authorized,
        "antigravity_flash_quota_exhausted": antigravity_flash_quota_exhausted,
        "antigravity_pro_quota_exhausted": antigravity_pro_quota_exhausted,
    }

    if current_tier is None:
        return "deterministic_local", audit

    if current_tier == "deterministic_local":
        return "primary_local_worker", audit

    if current_tier == "primary_local_worker":
        return "local_fallback_reviewer", audit

    if current_tier == "local_fallback_reviewer":
        if task_requires_stronger_reasoning:
            if antigravity_pro_available and not antigravity_pro_quota_exhausted:
                return "antigravity_pro", audit
            audit["skipped_tier"] = "antigravity_pro_exhausted_or_unavailable"
            if codex_available:
                return "codex", audit
            if paid_authorized:
                return "paid_api_authorized", audit
            return None, {**audit, "status": "ESCALATION_BLOCKED"}
        else:
            if antigravity_flash_available and not antigravity_flash_quota_exhausted:
                return "antigravity_flash", audit
            audit["skipped_tier"] = "antigravity_flash_exhausted_or_unavailable"
            if antigravity_pro_available and not antigravity_pro_quota_exhausted:
                return "antigravity_pro", audit
            audit["skipped_tier_2"] = "antigravity_pro_exhausted_or_unavailable"
            if codex_available:
                return "codex", audit
            if paid_authorized:
                return "paid_api_authorized", audit
            return None, {**audit, "status": "ESCALATION_BLOCKED"}

    if current_tier == "antigravity_flash":
        if antigravity_pro_available and not antigravity_pro_quota_exhausted:
            return "antigravity_pro", audit
        audit["skipped_tier"] = "antigravity_pro_exhausted_or_unavailable"
        if codex_available:
            return "codex", audit
        if paid_authorized:
            return "paid_api_authorized", audit
        return None, {**audit, "status": "ESCALATION_BLOCKED"}

    if current_tier == "antigravity_pro":
        if codex_available:
            return "codex", audit
        if paid_authorized:
            return "paid_api_authorized", audit
        return None, {**audit, "status": "STOP_PAID_API_NOT_AUTHORIZED"}

    if current_tier == "codex":
        if paid_authorized:
            return "paid_api_authorized", audit
        return None, {**audit, "status": "STOP_PAID_API_NOT_AUTHORIZED"}

    return None, {**audit, "status": "UNKNOWN_TIER"}


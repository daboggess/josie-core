from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from supervisor import VERSION
    from supervisor.authority import denied_events, policy_summary, requested_capabilities
    from supervisor.launcher import launch
    from supervisor.ollama import preflight
    from supervisor.policy import classify_premature_stop, decide, should_fallback, should_retry
    from supervisor.receipts import write_receipt
    from supervisor.verifier import attribute_changes, changed_paths, run_acceptance, scope_violations, snapshot
    from supervisor.work_order import ValidationError, WorkOrder
else:
    from . import VERSION
    from .authority import denied_events, policy_summary, requested_capabilities
    from .launcher import launch
    from .ollama import preflight
    from .policy import classify_premature_stop, decide, should_fallback, should_retry
    from .receipts import write_receipt
    from .verifier import attribute_changes, changed_paths, run_acceptance, scope_violations, snapshot
    from .work_order import ValidationError, WorkOrder


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def resource_check(order: WorkOrder) -> dict:
    if order.raw["harness"] not in {"goose", "opencode", "aider"}:
        return {"ok": True, "reason": "NOT_REQUIRED"}
    try:
        from josie.local_code import load_thermal_policy, read_gpu_telemetry
        policy = load_thermal_policy(Path(__file__).resolve().parent.parent)
        sample = read_gpu_telemetry(policy)
    except Exception as exc:
        return {"ok": False, "reason": "THERMAL_TELEMETRY_UNAVAILABLE", "error": str(exc)}
    blocked = sample["temperature_c"] >= policy["block_new_job_c"]
    return {
        "ok": not blocked,
        "reason": "THERMAL_PREFLIGHT_BLOCKED" if blocked else "OK",
        "sample": sample,
        "limits": {
            "block_new_job_c": policy["block_new_job_c"],
            "terminate_active_c": policy["terminate_active_c"],
            "critical_c": policy["critical_c"],
        },
    }


VOLATILE_RUNTIME_SQLITE_FILES = {
    "data/josie.db",
    "data/josie.db-wal",
    "data/josie.db-shm",
}

TRIVIAL_BLOCKER_VALUES = {
    "", "none", "(none)", "n/a", "na", "nil", "nothing", "no",
    "no blockers", "none so far", "none reported", "false", "clear",
    "- none", "- (none)", "* none", "* (none)", "none.", "(none).",
}

BLOCKER_HEADER_PATTERN = re.compile(
    r"^(?:#{1,6}\s*|\*{1,2}\s*)?(?:blocked|blockers?)(?:\s*\(s\))?\s*:?\s*(.*)$",
    re.IGNORECASE,
)
NEXT_HEADER_PATTERN = re.compile(
    r"^(?:#{1,6}\s+\S|\*{1,2}[A-Za-z0-9_ -]+\*{1,2}:?|[A-Z][A-Za-z0-9_ -]{2,}:)",
    re.IGNORECASE,
)
UNABLE_TO_PROCEED_PATTERN = re.compile(
    r"\b(?:cannot\s+proceed|unable\s+to\s+proceed|can't\s+proceed)\b",
    re.IGNORECASE,
)
HARNESS_STEP_LIMIT_PATTERN = re.compile(
    r"\b(?:maximum\s+number\s+of\s+steps(?:\s+allowed)?(?:\s+for\s+this\s+task)?\s+has\s+been\s+reached|"
    r"step\s+limit\s+reached|step\s+ceiling\s+reached|reached\s+(?:the\s+)?(?:maximum|max)\s+(?:number\s+of\s+)?steps)\b",
    re.IGNORECASE,
)


def _clean_item(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"^[-*+•\d.)\s]+", "", cleaned).strip()
    cleaned = cleaned.strip("\"'")
    cleaned = re.sub(r"^[(\[]\s*|\s*[)\]]$", "", cleaned).strip()
    cleaned = cleaned.strip("\"'")
    return cleaned.rstrip(".!?,;: ")


def detect_harness_step_limit(text_chunks: list[str]) -> bool:
    full_text = "\n".join(text_chunks)
    return bool(HARNESS_STEP_LIMIT_PATTERN.search(full_text))


def worker_targeted_files(tool_events: list[dict], workspace: Path) -> set[str]:
    targeted = set()
    for event in tool_events:
        tool = str(event.get("tool") or "")
        inp = event.get("input") or {}
        if tool in {"write", "edit", "apply_patch", "text_editor", "patch_file"}:
            if isinstance(inp, dict):
                for k in ("filePath", "file_path", "path", "target_file", "file"):
                    val = inp.get(k)
                    if isinstance(val, str) and val.strip():
                        try:
                            rel = Path(val).resolve().relative_to(workspace.resolve()).as_posix()
                            targeted.add(rel)
                        except (ValueError, OSError):
                            targeted.add(val.replace("\\", "/").strip("/"))
        elif tool in {"bash", "shell"}:
            cmd = (inp.get("command") or inp.get("cmd") or "") if isinstance(inp, dict) else str(inp)
            for f in VOLATILE_RUNTIME_SQLITE_FILES:
                if f in cmd or f.replace("/", "\\") in cmd:
                    targeted.add(f)
    return targeted


def detect_blocker(text_chunks: list[str]) -> bool:
    full_text = "\n".join(text_chunks)
    lines = full_text.splitlines()

    # 1. Check for explicit cannot / unable to proceed statements outside negative context
    for line in lines:
        if UNABLE_TO_PROCEED_PATTERN.search(line):
            low = line.strip().lower()
            if not any(neg in low for neg in ("do not", "don't", "never", "without")):
                if not HARNESS_STEP_LIMIT_PATTERN.search(low):
                    return True

    # 2. Structured section detection
    i = 0
    while i < len(lines):
        line = lines[i]
        header_match = BLOCKER_HEADER_PATTERN.match(line.strip())
        if header_match:
            inline_content = header_match.group(1).strip()
            section_items = []
            if inline_content:
                section_items.append(inline_content)
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    j += 1
                    continue
                if NEXT_HEADER_PATTERN.match(next_line):
                    break
                section_items.append(next_line)
                j += 1
            i = j - 1

            substantive = False
            for item in section_items:
                clean = _clean_item(item)
                if clean and clean not in TRIVIAL_BLOCKER_VALUES:
                    if not HARNESS_STEP_LIMIT_PATTERN.search(clean):
                        substantive = True
                        break
            if substantive:
                return True
        i += 1

    return False


def event_activity(path: Path) -> tuple[list[str], bool, list[dict]]:
    tools, text, events = [], [], []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            lowered = line.lower()
            match = next((name for name in (
                "shell", "edit", "write", "read", "tree", "grep", "glob"
            ) if f"▸ {name}" in lowered), None)
            if match:
                tools.append(match)
            if any(k in lowered for k in ("applied edit", "applied whole", "edit applied", "updated", "wrote", "commit", "tokens")):
                tools.append("edit")
            text.append(line)
            continue
        part = event.get("part") or {}
        event_type = str(event.get("type") or "")
        if event_type == "tool_use" and isinstance(part.get("tool"), str):
            tools.append(part["tool"])
            state = part.get("state") or {}
            events.append({
                "tool": part["tool"], "status": state.get("status"),
                "input": state.get("input"),
            })
        elif event_type in {"tool_call", "tool_request", "tool_response"}:
            tool_name = event.get("tool_name") or event.get("name") or part.get("tool")
            if isinstance(tool_name, str):
                tools.append(tool_name)
        elif event.get("type") == "text":
            text.append(str(part.get("text", "") or event.get("text", "")))
        for content in ((event.get("message") or {}).get("content") or []):
            if content.get("type") == "toolRequest":
                call = content.get("toolCall") or {}
                value = call.get("value") or {}
                name = value.get("name")
                if isinstance(name, str):
                    tools.append(name)
                    events.append({
                        "tool": name, "status": call.get("status"),
                        "input": value.get("arguments"), "call_id": content.get("id"),
                    })
            elif content.get("type") == "toolResponse":
                result = content.get("toolResult") or {}
                value = result.get("value") or {}
                structured = value.get("structuredContent") or {}
                events.append({
                    "tool_response": content.get("id"), "status": result.get("status"),
                    "exit_code": structured.get("exit_code"),
                    "is_error": value.get("isError", False),
                })
            elif content.get("type") == "text":
                text.append(str(content.get("text") or ""))
    blocker = detect_blocker(text)
    return tools, blocker, events


def _execute_one(path: Path, raw_override: dict | None = None) -> tuple[dict, Path | None]:
    transitions = [{"state": "RECEIVED", "at": now()}, {"state": "VALIDATING", "at": now()}]
    raw = raw_override if raw_override is not None else json.loads(path.read_text(encoding="utf-8"))
    try:
        order = WorkOrder.validate(raw)
    except ValidationError as exc:
        return {"schema_version": "1", "supervisor_version": VERSION, "job_id": raw.get("job_id") if isinstance(raw, dict) else None, "state_transitions": transitions + [{"state": "FAIL", "at": now()}], "final_status": "FAIL", "reason": "VALIDATION_FAIL", "error": str(exc), "worker_launched": False}, None
    receipt_dir = Path(order.raw["receipt_destination"])
    attempt = 1
    transitions.append({"state": "PREFLIGHT", "at": now()})
    resources = resource_check(order)
    if not resources["ok"]:
        transitions.append({"state": "BLOCKED", "at": now()})
        receipt = {"schema_version": "1", "supervisor_version": VERSION,
            "job_id": order.raw["job_id"], "attempt": attempt,
            "harness": order.raw["harness"], "requested_model": order.raw["model"],
            "workspace": str(order.workspace), "state_transitions": transitions,
            "resource_preflight": resources, "worker_launched": False,
            "final_status": "BLOCKED", "reason": resources["reason"]}
        return receipt, write_receipt(receipt_dir, receipt)
    if order.raw["harness"] in {"goose", "opencode", "aider"}:
        check_model = order.raw["model"].split("/", 1)[-1]
        pf = preflight(order.raw.get("ollama_url", "http://127.0.0.1:11434"), check_model)
        if not pf["ok"] and ":" not in check_model:
            pf_latest = preflight(order.raw.get("ollama_url", "http://127.0.0.1:11434"), f"{check_model}:latest")
            if pf_latest["ok"]:
                pf = pf_latest
    else:
        pf = {"ok": True, "reason": "MOCK_PREFLIGHT"}
    if not pf["ok"]:
        transitions.append({"state": "BLOCKED", "at": now()})
        receipt = {"schema_version": "1", "supervisor_version": VERSION, "job_id": order.raw["job_id"], "attempt": attempt, "harness": order.raw["harness"], "requested_model": order.raw["model"], "workspace": str(order.workspace), "state_transitions": transitions, "preflight": pf, "worker_launched": False, "final_status": "BLOCKED", "reason": pf["reason"]}
        return receipt, write_receipt(receipt_dir, receipt)
    previous_receipt = None
    for attempt in range(1, order.raw["max_attempts"] + 1):
        attempt_transitions = list(transitions)
        run_id = f"{order.raw['job_id']}-attempt-{attempt}-{dt.datetime.now().strftime('%Y%m%dT%H%M%S%f')}"
        log_dir = receipt_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path, stderr_path = log_dir / f"{run_id}.stdout.log", log_dir / f"{run_id}.stderr.log"
        receipt_id = str(uuid.uuid4())
        receipt_target = receipt_dir / f"{receipt_id}.json"
        supervisor_artifacts = [stdout_path, stderr_path, receipt_target]
        if order.raw["harness"] == "aider":
            supervisor_artifacts.extend([
                stdout_path.with_suffix(".aider.chat.history.md"),
                stdout_path.with_suffix(".aider.input.history"),
            ])
        stdout_path.touch(exist_ok=False)
        stderr_path.touch(exist_ok=False)
        attempt_transitions.append({"state": "SNAPSHOT", "at": now()})
        before = snapshot(order.workspace, order.allowed_changed_paths)
        attempt_transitions.append({"state": "WORKER_RUNNING", "at": now()})
        started = now()
        try:
            worker = launch(order, stdout_path, stderr_path, retry=attempt > 1)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            ended = now()
            attempt_transitions.append({"state": "FAIL", "at": ended})
            receipt = {
                "schema_version": "1", "supervisor_version": VERSION,
                "job_id": order.raw["job_id"], "attempt": attempt,
                "max_attempts": order.raw["max_attempts"], "harness": order.raw["harness"],
                "harness_executable": str(order.raw.get("harness_executable", "")),
                "harness_version": "NOT_RUN", "requested_model": order.raw["model"],
                "workspace": str(order.workspace), "started_at": started, "ended_at": ended,
                "elapsed_seconds": 0, "state_transitions": attempt_transitions,
                "worker_launched": False, "preflight": pf, "final_status": "FAIL",
                "reason": "LAUNCH_ERROR", "error": str(exc), "acceptance_results": [],
                "changed_files": [], "tool_activity": [],
            }
            return receipt, write_receipt(receipt_dir, receipt, receipt_id)
        ended = now()
        attempt_transitions.append({"state": "VERIFYING", "at": now()})
        after = snapshot(order.workspace, order.allowed_changed_paths)
        observed_changes = changed_paths(before, after)
        changes, owned_relative = attribute_changes(
            observed_changes, order.workspace, supervisor_artifacts
        )
        tool_names, blocker_reported, tool_events = event_activity(stdout_path)
        targeted = worker_targeted_files(tool_events, order.workspace)
        changes = [
            path for path in changes
            if path.replace("\\", "/").strip("/") not in VOLATILE_RUNTIME_SQLITE_FILES
            or path.replace("\\", "/").strip("/") in targeted
        ]
        violations = scope_violations(changes, order)
        acceptance = run_acceptance(order, changes)
        side_effect_policy = policy_summary(order.raw)
        side_effect_policy["denied_actions"] = denied_events(stdout_path, requested_capabilities(order.raw))
        step_limit_reported = detect_harness_step_limit([
            line for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines()
        ]) if stdout_path.is_file() else False
        if changes and "edit" not in tool_names:
            tool_names.append("edit")
        status, reason = decide(launched=True, preflight_ok=True, timed_out=worker["timed_out"], exit_code=worker["exit_code"], violations=violations, acceptance=acceptance)
        acceptance_passed = bool(acceptance and all(item.get("passed") is True for item in acceptance) and not violations)
        if worker.get("stalled"):
            status, reason = "FAIL", "FAIL_STALL"
        elif (order.raw["harness"] in {"goose", "opencode", "aider"}
                and worker["timed_out"] and not tool_names):
            status = "FAIL"
            reason = "FAIL_STALL"
        elif (order.raw["harness"] in {"goose", "opencode", "aider"}
                or order.raw.get("requires_modification", False)) and not tool_names:
            status, reason = "FAIL", "FAIL_NO_TOOL_ACTIVITY"
        elif acceptance_passed:
            pass
        elif blocker_reported:
            status, reason = "BLOCKED", "WORKER_BLOCKED"
        elif step_limit_reported:
            status, reason = "FAIL", "HARNESS_STEP_LIMIT"
        if attempt == 1 and reason == "FAIL_ACCEPTANCE" and classify_premature_stop(
                requires_modification=order.raw.get("requires_modification", False),
                exit_code=worker["exit_code"], timed_out=worker["timed_out"],
                violations=violations, changes=changes, acceptance=acceptance,
                tool_names=tool_names, blocker_reported=blocker_reported,
                denied_actions=side_effect_policy["denied_actions"]):
            reason = "PREMATURE_STOP"
        attempt_transitions.append({"state": status, "at": now()})
        receipt = {"schema_version": "1", "supervisor_version": VERSION, "job_id": order.raw["job_id"], "attempt": attempt, "max_attempts": order.raw["max_attempts"], "previous_receipt": str(previous_receipt) if previous_receipt else None, "harness": order.raw["harness"], "harness_executable": worker["argv"][0], "harness_version": worker["version"], "requested_model": order.raw["model"], "discovered_model": pf.get("discovered_model"), "workspace": str(order.workspace), "argv": worker["argv"], "environment_evidence": worker.get("environment_evidence", {}), "started_at": started, "ended_at": ended, "elapsed_seconds": worker["elapsed_seconds"], "pid": worker["pid"], "liveness": worker.get("liveness", {}), "state_transitions": attempt_transitions, "timed_out": worker["timed_out"], "stalled": worker.get("stalled", False), "cleanup": worker["cleanup"], "exit_code": worker["exit_code"], "stdout_path": str(stdout_path), "stderr_path": str(stderr_path), "before_state": before, "observed_changed_paths": observed_changes, "worker_changed_paths": changes, "supervisor_owned_artifacts": [str(path) for path in supervisor_artifacts], "supervisor_owned_workspace_paths": owned_relative, "changed_files": changes, "scope_violations": violations, "acceptance_results": acceptance, "preflight": pf, "resource_preflight": resources, "resource_postflight": resource_check(order), "side_effect_policy": side_effect_policy, "tool_activity": tool_names, "tool_events": tool_events[-40:], "blocker_reported": blocker_reported, "worker_launched": True, "final_status": status, "reason": reason}
        receipt_path = write_receipt(receipt_dir, receipt, receipt_id)
        if not should_retry(reason, attempt, order.raw["max_attempts"]):
            return receipt, receipt_path
        previous_receipt = receipt_path
    return receipt, receipt_path


def execute(path: Path) -> tuple[dict, Path | None]:
    """Execute one validated order; `coder` deterministically routes Goose (Ornith) -> Goose (Qwen) -> OpenCode (Qwen)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    order = WorkOrder.validate(raw)
    if order.raw["harness"] != "coder":
        return _execute_one(path, raw)

    receipt_dir = Path(raw["receipt_destination"])

    # 1. Primary: Goose + josie-qual-ornith-1.5-9b-q6 @ 8192
    primary = dict(raw)
    primary.update({
        "harness": "goose",
        "model": "josie-qual-ornith-1.5-9b-q6",
        "context_limit": 8192,
        "harness_executable": raw.get("primary_harness_executable")
            or r"I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe",
    })
    primary.pop("harness_config", None)
    primary.pop("agent", None)
    primary.pop("agent_profile", None)
    primary_receipt, primary_path = _execute_one(path, primary)
    if primary_receipt.get("final_status") == "PASS" or not should_fallback(
            str(primary_receipt.get("reason"))):
        return primary_receipt, primary_path

    # 2. Fallback 1: Goose + qwen3:14b @ 8192
    fallback_1 = dict(raw)
    fallback_1.update({
        "harness": "goose",
        "model": "qwen3:14b",
        "context_limit": 8192,
        "harness_executable": raw.get("primary_harness_executable")
            or r"I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe",
    })
    fallback_1.pop("harness_config", None)
    fallback_1.pop("agent", None)
    fallback_1.pop("agent_profile", None)
    fb1_receipt, fb1_path = _execute_one(path, fallback_1)
    if fb1_receipt.get("final_status") == "PASS" or not should_fallback(
            str(fb1_receipt.get("reason"))):
        aggregate = {
            **fb1_receipt,
            "schema_version": "1", "supervisor_version": VERSION,
            "job_id": raw["job_id"],
            "route": "goose-ornith-primary-goose-qwen-fallback",
            "primary_harness": "goose", "primary_model": "josie-qual-ornith-1.5-9b-q6",
            "fallback_harness": "goose", "fallback_model": "qwen3:14b",
            "fallback_occurred": True,
            "fallback_event": {
                "from": "goose/josie-qual-ornith-1.5-9b-q6",
                "to": "goose/qwen3:14b",
                "reason": primary_receipt.get("reason"),
                "at": now(),
                "primary_receipt": str(primary_path),
            },
            "attempt_receipts": [str(value) for value in (primary_path, fb1_path) if value],
            "selected_harness": fb1_receipt.get("harness"),
        }
        aggregate_path = write_receipt(receipt_dir, aggregate)
        return aggregate, aggregate_path

    # 3. Fallback 2: OpenCode + ollama/qwen3:14b
    fallback_2 = dict(raw)
    fallback_2.update({
        "harness": "opencode",
        "model": "ollama/qwen3:14b",
        "harness_executable": raw.get("fallback_harness_executable")
            or r"I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe",
    })
    fb2_receipt, fb2_path = _execute_one(path, fallback_2)
    aggregate = {
        **fb2_receipt,
        "schema_version": "1", "supervisor_version": VERSION,
        "job_id": raw["job_id"],
        "route": "goose-ornith-primary-opencode-qwen-fallback",
        "primary_harness": "goose", "primary_model": "josie-qual-ornith-1.5-9b-q6",
        "fallback_harness": "opencode", "fallback_model": "ollama/qwen3:14b",
        "fallback_occurred": True,
        "fallback_event": {
            "from": "goose/qwen3:14b",
            "to": "opencode/ollama/qwen3:14b",
            "reason": fb1_receipt.get("reason"),
            "at": now(),
            "primary_receipt": str(primary_path),
            "fallback_1_receipt": str(fb1_path),
        },
        "attempt_receipts": [str(value) for value in (primary_path, fb1_path, fb2_path) if value],
        "selected_harness": fb2_receipt.get("harness"),
    }
    aggregate_path = write_receipt(receipt_dir, aggregate)
    return aggregate, aggregate_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work_order", type=Path)
    args = parser.parse_args()
    try:
        receipt, path = execute(args.work_order)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"final_status": "ERROR", "reason": "SUPERVISOR_ERROR", "error": str(exc)}))
        return 2
    print(json.dumps({"final_status": receipt["final_status"], "reason": receipt["reason"], "receipt": str(path) if path else None}))
    return 0 if receipt["final_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

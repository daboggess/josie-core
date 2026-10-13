"""Outbound Local Wake Adapter for Sophie (ChatGPT).

Connects to Dustin's existing authenticated local ChatGPT session via Chrome
DevTools Protocol (CDP) to automatically trigger 'relay' without manual user
interaction, while strictly preserving:
1. Security & Privacy: No credentials extracted, no session cookies saved,
   operates strictly against Dustin's local browser session.
2. Decoupled Authority: A wake transport attempt only yields transport telemetry;
   it never satisfies a wait. WAITING_FOR_SOPHIE resolves exclusively from an
   authoritative matching Slack reply.
3. Deduplication: State persisted to data/slack-relay/wake_intents.json prevents
   duplicate wake signals for the same wait key.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import uuid

logger = logging.getLogger("josie.wake_adapter")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WAKE_INTENTS_FILE = PROJECT_ROOT / "data" / "slack-relay" / "wake_intents.json"
DEFAULT_CDP_URL = os.environ.get("JOSIE_CDP_URL", "http://127.0.0.1:9222")
PERSISTENT_DEFAULT_WORKER_ID = "dd7ef29a-4ebd-4002-9041-68935ccd79c2"
CANONICAL_WORKER_LS_ADDRESS = "127.0.0.1:50588"
CANONICAL_WORKER_CSRF_TOKEN = "883efbc7-9bf1-4c6c-bd2c-8f1ca2c4f0de"

DEFAULT_WORKER_CONVERSATION_ID = os.environ.get(
    "JOSIE_WORKER_CONVERSATION_ID", PERSISTENT_DEFAULT_WORKER_ID
)
DEFAULT_WORKER_LS_ADDRESS = os.environ.get(
    "JOSIE_WORKER_LS_ADDRESS", CANONICAL_WORKER_LS_ADDRESS
)
DEFAULT_WORKER_CSRF_TOKEN = os.environ.get(
    "JOSIE_WORKER_CSRF_TOKEN", CANONICAL_WORKER_CSRF_TOKEN
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_wake_intents(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Load persisted wake intents from disk."""
    file_path = path or DEFAULT_WAKE_INTENTS_FILE
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception as exc:
        logger.warning(f"Failed to read wake intents from {file_path}: {exc}")
        return []


def save_wake_intents(intents: list[dict[str, Any]], path: Optional[Path] = None) -> None:
    """Persist wake intents to disk atomically."""
    file_path = path or DEFAULT_WAKE_INTENTS_FILE
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(intents, indent=2), encoding="utf-8")
    temp_path.replace(file_path)


def find_wake_intent(
    mission_id: str,
    wait_id: str,
    request_message_id: str,
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Find existing wake intent matching the deduplication key."""
    intents = load_wake_intents(path)
    for it in intents:
        if (
            it.get("mission_id") == mission_id
            and it.get("wait_id") == wait_id
            and it.get("request_message_id") == request_message_id
        ):
            return it
    return None


def trigger_sophie_wake(
    mission_id: str,
    wait_id: str,
    request_message_id: str,
    request_ts: str,
    thread_ts: str,
    config: Optional[Any] = None,
    cdp_url: str = DEFAULT_CDP_URL,
    intents_path: Optional[Path] = None,
    force_retry: bool = False,
) -> dict[str, Any]:
    """Execute outbound wake intent against local ChatGPT session via CDP.

    Deduplication key: mission_id + wait_id + request_message_id.
    Returns structured wake telemetry record. Fails closed and never raises.
    """
    existing = find_wake_intent(mission_id, wait_id, request_message_id, intents_path)
    if existing and not force_retry:
        logger.info(
            f"[WAKE_ADAPTER] Wake intent already triggered for {mission_id}:{wait_id}:{request_message_id} "
            f"(attempt_id={existing.get('wake_attempt_id')}, outcome={existing.get('outcome')})"
        )
        return {
            **existing,
            "already_triggered": True,
        }

    attempt_id = f"WAKE-{uuid.uuid4().hex[:8].upper()}"
    now_str = _utc_now_iso()
    outcome = "PENDING"
    error_msg: Optional[str] = None
    tab_url: Optional[str] = None

    turn_telemetry: Optional[dict[str, Any]] = None

    try:
        import concurrent.futures
        from playwright.sync_api import sync_playwright

        def _perform_cdp_wake():
            logger.info(f"[WAKE_ADAPTER] Attempting CDP connection to {cdp_url} (attempt={attempt_id})...")
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(cdp_url, timeout=4000)
                target_page = None

                for context in browser.contexts:
                    for page in context.pages:
                        url = page.url.lower()
                        if "chatgpt.com" in url or "openai.com" in url:
                            target_page = page
                            t_url = page.url
                            break
                    if target_page:
                        break

                if not target_page:
                    return "CHATGPT_TAB_NOT_FOUND", None, "Connected to browser via CDP but no ChatGPT tab was found in open contexts.", None

                logger.info(f"[WAKE_ADAPTER] Found ChatGPT tab: {t_url}. Checking idle state...")
                import time

                # 1. Verify not currently generating
                stop_btn = target_page.locator("button[aria-label='Stop generating'], button[data-testid='stop-button']")
                try:
                    for _ in range(10):
                        if stop_btn.count() == 0 or not stop_btn.first.is_visible():
                            break
                        time.sleep(0.5)
                    else:
                        return "CHATGPT_BUSY", t_url, "ChatGPT tab is currently generating a response (stop button visible).", None
                except Exception:
                    pass

                # 2. Record pre-wake user message count & last user text
                count_before = 0
                last_text_before = ""
                try:
                    dom_info = target_page.evaluate("""() => {
                        const userMsgs = document.querySelectorAll('div[class*="bg-user-message"]');
                        return {
                            count: userMsgs.length,
                            lastText: userMsgs.length > 0 ? (userMsgs[userMsgs.length - 1].innerText || '').trim() : ''
                        };
                    }""")
                    if isinstance(dom_info, dict):
                        count_before = dom_info.get("count", 0)
                        last_text_before = dom_info.get("lastText", "")
                except Exception:
                    pass

                logger.info(f"[WAKE_ADAPTER] Pre-wake DOM state: count={count_before}, last_text='{last_text_before[:50]}'")

                # 3. Focus composer and type 'relay' with synthetic events
                input_selector = "#prompt-textarea, div[contenteditable='true'], textarea#prompt-textarea"
                inp = target_page.wait_for_selector(input_selector, timeout=5000)
                inp.click()
                time.sleep(0.2)
                target_page.keyboard.press("Control+A")
                target_page.keyboard.press("Backspace")
                target_page.keyboard.type("relay", delay=30)
                time.sleep(0.4)

                # 4. Find and click Send button
                send_btn = target_page.locator("button[aria-label='Send'], button[data-testid='send-button']").last
                clicked_send = False
                for _ in range(25):
                    try:
                        c = send_btn.count()
                        if isinstance(c, (int, float)) and c > 0 and not send_btn.evaluate("el => el.disabled"):
                            send_btn.click()
                            clicked_send = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.2)

                if not clicked_send:
                    target_page.keyboard.press("Enter")

                # 5. Causal Verification: Verify that a distinct new turn appeared in the DOM
                turn_verified = False
                count_after = count_before
                last_text_after = ""
                for _ in range(30):
                    time.sleep(0.2)
                    try:
                        new_info = target_page.evaluate("""() => {
                            const userMsgs = document.querySelectorAll('div[class*="bg-user-message"]');
                            const stopBtn = document.querySelectorAll('button[aria-label="Stop"], button[aria-label="Stop generating"]').length;
                            const prose = document.querySelector('#prompt-textarea, div.ProseMirror');
                            const composerEmpty = prose ? (prose.innerText || '').trim() === '' : false;
                            const agentTurn = document.querySelectorAll('[data-chatgpt-agent-turn-start]').length;
                            return {
                                count: userMsgs.length,
                                lastText: userMsgs.length > 0 ? (userMsgs[userMsgs.length - 1].innerText || '').trim() : '',
                                stopBtn,
                                composerEmpty,
                                agentTurn
                            };
                        }""")
                        if isinstance(new_info, dict):
                            count_after = new_info.get("count", 0)
                            last_text_after = new_info.get("lastText", "")
                            composer_empty = new_info.get("composerEmpty", False)
                            has_stop_or_turn = new_info.get("stopBtn", 0) > 0 or new_info.get("agentTurn", 0) > 0
                            
                            if (count_after > count_before and "relay" in last_text_after.lower()) or (
                                composer_empty and "relay" in last_text_after.lower() and (clicked_send or has_stop_or_turn)
                            ):
                                turn_verified = True
                                break
                    except Exception:
                        pass

                telemetry = {
                    "count_before": count_before,
                    "count_after": count_after,
                    "last_text_before": last_text_before[:100],
                    "last_text_after": last_text_after[:100],
                    "verified_in_dom": turn_verified,
                    "turn_created_at": _utc_now_iso(),
                }

                if not turn_verified:
                    logger.warning(f"[WAKE_ADAPTER] Turn verification failed: before={count_before}, after={count_after}")
                    return "WAKE_DOM_VERIFY_FAILED", t_url, f"Relay submitted but new user turn not detected in DOM (before={count_before}, after={count_after})", telemetry

                logger.info(f"[WAKE_ADAPTER] Successfully submitted and verified 'relay' in ChatGPT tab (turn count: {count_before} -> {count_after}).")
                return "SUCCESS", t_url, None, telemetry

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            outcome, tab_url, error_msg, turn_telemetry = pool.submit(_perform_cdp_wake).result(timeout=25)

    except Exception as exc:
        outcome = "CDP_UNREACHABLE"
        error_msg = str(exc)
        logger.warning(f"[WAKE_ADAPTER] CDP connection failed: {error_msg}")

    record = {
        "wake_attempt_id": attempt_id,
        "mission_id": mission_id,
        "wait_id": wait_id,
        "request_message_id": request_message_id,
        "request_ts": request_ts,
        "thread_ts": thread_ts,
        "attempted_at": now_str,
        "outcome": outcome,
        "retry_count": (existing.get("retry_count", 0) + 1) if existing else 0,
        "transport_version": "cdp_v1",
        "cdp_url": cdp_url,
        "tab_url": tab_url,
        "turn_telemetry": turn_telemetry,
        "error": error_msg,
        "already_triggered": False,
    }

    intents = load_wake_intents(intents_path)
    # Update existing or append new
    updated = False
    for i, it in enumerate(intents):
        if (
            it.get("mission_id") == mission_id
            and it.get("wait_id") == wait_id
            and it.get("request_message_id") == request_message_id
        ):
            intents[i] = record
            updated = True
            break
    if not updated:
        intents.append(record)

    save_wake_intents(intents, intents_path)
    return record


def find_worker_wake_intent(
    mission_id: str,
    wait_id: str,
    reply_message_id: str,
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Find existing worker wake intent matching the deduplication key."""
    intents = load_wake_intents(path)
    for it in intents:
        if (
            it.get("wake_target") == "ANTIGRAVITY_WORKER"
            and it.get("mission_id") == mission_id
            and it.get("wait_id") == wait_id
            and it.get("reply_message_id") == reply_message_id
        ):
            return it
    return None


def is_live_worker_enabled() -> bool:
    """Check if spawning live Antigravity worker sessions via IPC is permitted.

    Fails closed by default to prevent routine unit tests or unexpected callers from
    spawning live cascades or interacting with live developer sessions.
    Only returns True if explicitly enabled via JOSIE_ALLOW_LIVE_WORKER=1.
    """
    if os.environ.get("JOSIE_DISABLE_LIVE_WORKER") == "1":
        return False
    if os.environ.get("JOSIE_ALLOW_LIVE_WORKER") == "1":
        return True
    if "unittest" in sys.modules or "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return False


def find_worker_wake_by_work_order(
    work_order_id: str,
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Find existing worker wake intent by work order ID."""
    if not work_order_id:
        return None
    intents = load_wake_intents(path)
    for it in intents:
        if (
            it.get("wake_target") == "ANTIGRAVITY_WORKER"
            and it.get("work_order_id") == work_order_id
        ):
            return it
    return None


def start_worker_cascade_session(
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
) -> Optional[str]:
    """Start a fresh, dedicated Antigravity cascade session via Language Server IPC.

    Guarded: Never spawns live cascade sessions unless explicitly enabled via JOSIE_ALLOW_LIVE_WORKER=1.
    """
    if not is_live_worker_enabled():
        logger.info("[WAKE_ADAPTER] Live worker session spawning disabled in current environment; skipping StartCascade.")
        return None

    target_ls_address = ls_address or os.environ.get("ANTIGRAVITY_LS_ADDRESS", DEFAULT_WORKER_LS_ADDRESS)
    target_csrf_token = csrf_token or os.environ.get("ANTIGRAVITY_CSRF_TOKEN", DEFAULT_WORKER_CSRF_TOKEN)
    try:
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = f"http://{target_ls_address}/exa.language_server_pb.LanguageServerService/StartCascade"
        headers = {
            "Content-Type": "application/json",
            "x-codeium-csrf-token": target_csrf_token,
        }
        body = json.dumps({"source": "CORTEX_TRAJECTORY_SOURCE_CLI"}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers)
        resp = opener.open(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("cascadeId")
    except Exception as exc:
        logger.warning(f"[WAKE_ADAPTER] Failed to start new cascade session: {exc}")
        return None


def _get_ls_candidate_tokens(csrf_token: Optional[str] = None) -> list[str]:
    tokens: list[str] = []
    if csrf_token and csrf_token.strip():
        tokens.append(csrf_token.strip())
    if DEFAULT_WORKER_CSRF_TOKEN not in tokens:
        tokens.append(DEFAULT_WORKER_CSRF_TOKEN)
    if CANONICAL_WORKER_CSRF_TOKEN not in tokens:
        tokens.append(CANONICAL_WORKER_CSRF_TOKEN)
    env_token = os.environ.get("ANTIGRAVITY_CSRF_TOKEN")
    if env_token and env_token.strip() and env_token not in tokens:
        tokens.append(env_token.strip())
    return tokens


def check_worker_status(
    session_id: str,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
) -> dict[str, Any]:
    """Single non-blocking probe of Language Server GetCascadeTrajectory."""
    target_ls_address = ls_address or DEFAULT_WORKER_LS_ADDRESS
    candidate_tokens = _get_ls_candidate_tokens(csrf_token)
    import urllib.error
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    probe_url = f"http://{target_ls_address}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory"
    body = json.dumps({"cascadeId": session_id}).encode("utf-8")
    data = None
    try:
        for token in candidate_tokens:
            headers = {
                "Content-Type": "application/json",
                "x-codeium-csrf-token": token,
            }
            try:
                req = urllib.request.Request(probe_url, data=body, headers=headers)
                resp = opener.open(req, timeout=5)
                data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as h_err:
                if h_err.code == 401 and token != candidate_tokens[-1]:
                    continue
                raise
        if not data:
            return {
                "status": "ERROR",
                "session_id": session_id,
                "response_text": "",
                "steps_count": 0,
                "error": "Empty response from Language Server",
            }
        steps = data.get("trajectory", {}).get("steps", [])
        if steps:
            last_step = steps[-1]
            if "plannerResponse" in last_step:
                pr = last_step["plannerResponse"]
                resp_text = pr.get("response", "")
                if resp_text and not pr.get("toolCalls"):
                    return {
                        "status": "COMPLETED",
                        "session_id": session_id,
                        "response_text": resp_text,
                        "steps_count": len(steps),
                        "error": None,
                    }
            elif "errorMessage" in last_step:
                return {
                    "status": "ERROR",
                    "session_id": session_id,
                    "response_text": "",
                    "steps_count": len(steps),
                    "error": str(last_step.get("errorMessage")),
                }
        return {
            "status": "PENDING",
            "session_id": session_id,
            "response_text": "",
            "steps_count": len(steps),
            "error": None,
        }
    except Exception as exc:
        logger.warning(f"[WAKE_ADAPTER] Probe error: {exc}")
        return {
            "status": "PROBE_ERROR",
            "session_id": session_id,
            "response_text": "",
            "steps_count": 0,
            "error": str(exc),
        }


def poll_worker_completion(
    session_id: str,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    timeout_seconds: int = 5,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    """Poll Language Server with bounded wait. Returns explicit PENDING status when in-progress."""
    import time
    start_time = time.time()
    last_steps_count = 0

    while True:
        status_info = check_worker_status(session_id, ls_address, csrf_token)
        st = status_info.get("status")
        last_steps_count = status_info.get("steps_count", 0)

        if st in ("COMPLETED", "ERROR"):
            return status_info

        if time.time() - start_time >= timeout_seconds:
            return {
                "status": "PENDING",
                "session_id": session_id,
                "response_text": "",
                "steps_count": last_steps_count,
                "error": None,
                "pending_reason": f"Worker execution in progress after bounded {timeout_seconds}s check",
            }

        time.sleep(poll_interval)


def trigger_worker_wake(
    mission_id: str,
    wait_id: str,
    reply_message_id: str,
    reply_ts: str,
    thread_ts: str,
    work_order_id: Optional[str] = None,
    session_id: Optional[str] = None,
    wake_payload: Optional[str] = None,
    ls_address: Optional[str] = None,
    csrf_token: Optional[str] = None,
    intents_path: Optional[Path] = None,
    force_retry: bool = False,
) -> dict[str, Any]:
    """Execute inbound/return wake intent against persistent Antigravity worker session via Language Server IPC.

    Idempotent: Reuses existing active session for the same work_order_id or (mission_id, wait_id, reply_message_id).
    Prevents duplicate active sessions for the same work order.
    Returns structured wake telemetry record. Fails closed and never raises.
    """
    # 1. Deduplication check: check exact key, or by work_order_id
    existing = find_worker_wake_intent(mission_id, wait_id, reply_message_id, intents_path)
    if not existing and work_order_id:
        existing = find_worker_wake_by_work_order(work_order_id, intents_path)

    if existing and not force_retry:
        logger.info(
            f"[WAKE_ADAPTER] Worker wake intent already triggered for {mission_id}:{wait_id}:{reply_message_id} "
            f"(work_order_id={work_order_id}, session_id={existing.get('session_id')}, "
            f"attempt_id={existing.get('wake_attempt_id')}, outcome={existing.get('outcome')})"
        )
        return {
            **existing,
            "already_triggered": True,
        }

    attempt_id = f"WORKER-WAKE-{uuid.uuid4().hex[:8].upper()}"
    now_str = _utc_now_iso()
    outcome = "PENDING"
    error_msg: Optional[str] = None

    target_ls_address = ls_address or DEFAULT_WORKER_LS_ADDRESS
    target_csrf_token = csrf_token or DEFAULT_WORKER_CSRF_TOKEN

    # Resolve target session:
    # 1. caller-provided
    # 2. existing session for this work order (prevent duplicate active sessions!)
    # 3. start fresh dynamic session (only if live worker enabled)
    # 4. default persistent fallback
    target_session_id = session_id
    if not target_session_id and existing and existing.get("session_id"):
        target_session_id = existing.get("session_id")
    if not target_session_id:
        target_session_id = DEFAULT_WORKER_CONVERSATION_ID

    # Validate session availability and submit wake via LanguageServerService IPC
    try:
        import urllib.error
        import urllib.request

        # Ensure we bypass any environment HTTP proxy for localhost
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        # 1. Probe session availability via GetCascadeTrajectory
        probe_url = f"http://{target_ls_address}/exa.language_server_pb.LanguageServerService/GetCascadeTrajectory"
        probe_body = json.dumps({"cascadeId": target_session_id}).encode("utf-8")
        candidate_tokens = _get_ls_candidate_tokens(csrf_token)
        working_token = candidate_tokens[0]
        probe_data = None
        probe_headers = {
            "Content-Type": "application/json",
            "x-codeium-csrf-token": working_token,
        }
        try:
            for token in candidate_tokens:
                p_hdrs = {
                    "Content-Type": "application/json",
                    "x-codeium-csrf-token": token,
                }
                probe_req = urllib.request.Request(probe_url, data=probe_body, headers=p_hdrs)
                try:
                    probe_resp = opener.open(probe_req, timeout=5)
                    probe_data = json.loads(probe_resp.read().decode("utf-8"))
                    working_token = token
                    probe_headers = p_hdrs
                    break
                except urllib.error.HTTPError as http_err:
                    if http_err.code == 401 and token != candidate_tokens[-1]:
                        continue
                    raise
            if not probe_data or "trajectory" not in probe_data:
                outcome = "WORKER_SESSION_UNAVAILABLE"
                error_msg = f"Trajectory {target_session_id} returned empty trajectory payload."
            else:
                session_status = probe_data.get("status", "UNKNOWN")
                logger.info(f"[WAKE_ADAPTER] Persistent worker session {target_session_id} found (status={session_status}).")
        except urllib.error.HTTPError as http_err:
            outcome = "WORKER_SESSION_UNAVAILABLE"
            error_msg = f"HTTP {http_err.code}: {http_err.read().decode('utf-8', errors='replace')}"
        except Exception as conn_err:
            outcome = "LS_UNREACHABLE"
            error_msg = f"Failed to connect to Language Server at {target_ls_address}: {conn_err}"

        # 2. If session is available, inject wake prompt via SendUserCascadeMessage
        if outcome == "PENDING":
            inject_url = f"http://{target_ls_address}/exa.language_server_pb.LanguageServerService/SendUserCascadeMessage"
            payload_text = wake_payload or (
                f"AUTONOMOUS_WORKER_WAKE: mission={mission_id} wait={wait_id} "
                f"reply_message_id={reply_message_id} thread={thread_ts}"
            )

            # Extract userConfig and userAgentSpec from existing trajectory if available
            user_config = None
            user_agent_spec = None
            if (
                isinstance(probe_data, dict)
                and "trajectory" in probe_data
                and isinstance(probe_data["trajectory"], dict)
            ):
                for step in probe_data["trajectory"].get("steps", []):
                    if isinstance(step, dict) and "userInput" in step:
                        u_inp = step["userInput"]
                        if isinstance(u_inp, dict):
                            if "userConfig" in u_inp:
                                user_config = u_inp["userConfig"]
                            elif "lastUserConfig" in u_inp:
                                user_config = u_inp["lastUserConfig"]
                            if "userAgentSpec" in u_inp:
                                user_agent_spec = u_inp["userAgentSpec"]

            if not user_config:
                user_config = {
                    "plannerConfig": {
                        "planModel": "MODEL_PLACEHOLDER_M318",
                        "useAiCredits": False,
                    }
                }
            if not user_agent_spec:
                user_agent_spec = {
                    "builtinAgent": {
                        "defaultAgent": {
                            "isGoogle": False,
                            "isInteractive": True,
                        }
                    }
                }

            inject_payload = {
                "cascadeId": target_session_id,
                "items": [{"text": payload_text}],
                "cascadeConfig": user_config,
                "userAgentSpec": user_agent_spec,
            }
            inject_body = json.dumps(inject_payload).encode("utf-8")
            inject_req = urllib.request.Request(inject_url, data=inject_body, headers=probe_headers)
            try:
                inject_resp = opener.open(inject_req, timeout=10)
                _ = inject_resp.read()
                outcome = "SUCCESS"
                logger.info(f"[WAKE_ADAPTER] Successfully injected worker wake into session {target_session_id}.")
            except urllib.error.HTTPError as inject_http_err:
                outcome = "INJECTION_FAILED"
                error_msg = f"HTTP {inject_http_err.code}: {inject_http_err.read().decode('utf-8', errors='replace')}"
            except Exception as inject_err:
                outcome = "INJECTION_FAILED"
                error_msg = f"Injection failed: {inject_err}"

    except Exception as exc:
        outcome = "ADAPTER_ERROR"
        error_msg = str(exc)
        logger.warning(f"[WAKE_ADAPTER] Worker wake unexpected error: {error_msg}")

    record = {
        "wake_attempt_id": attempt_id,
        "wake_target": "ANTIGRAVITY_WORKER",
        "mission_id": mission_id,
        "wait_id": wait_id,
        "work_order_id": work_order_id,
        "reply_message_id": reply_message_id,
        "reply_ts": reply_ts,
        "thread_ts": thread_ts,
        "session_id": target_session_id,
        "attempted_at": now_str,
        "outcome": outcome,
        "retry_count": (existing.get("retry_count", 0) + 1) if existing else 0,
        "transport_version": "antigravity_ipc_v1",
        "ls_address": target_ls_address,
        "error": error_msg,
        "already_triggered": False,
    }

    intents = load_wake_intents(intents_path)
    updated = False
    for i, it in enumerate(intents):
        if (
            it.get("wake_target") == "ANTIGRAVITY_WORKER"
            and (
                (it.get("mission_id") == mission_id and it.get("wait_id") == wait_id and it.get("reply_message_id") == reply_message_id)
                or (work_order_id and it.get("work_order_id") == work_order_id)
            )
        ):
            intents[i] = record
            updated = True
            break
    if not updated:
        intents.append(record)

    save_wake_intents(intents, intents_path)
    return record


def correlate_worker_completion(
    work_order_id: str,
    session_id: str,
    receipt_id: str,
    receipt_path: Optional[str] = None,
    path: Optional[Path] = None,
) -> Optional[dict[str, Any]]:
    """Correlate worker session with its authoritative completion receipt."""
    intents = load_wake_intents(path)
    matched = None
    for it in intents:
        if (
            it.get("wake_target") == "ANTIGRAVITY_WORKER"
            and (it.get("work_order_id") == work_order_id or (session_id and it.get("session_id") == session_id))
        ):
            it["receipt_id"] = receipt_id
            if receipt_path:
                it["receipt_path"] = str(receipt_path)
            it["correlated_at"] = _utc_now_iso()
            it["status"] = "COMPLETED"
            matched = it
            break
    if matched:
        save_wake_intents(intents, path)
    return matched


def detect_orphan_sessions(
    intents_path: Optional[Path] = None,
    missions_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Detect orphan worker sessions across recorded intents.

    An orphan session is an Antigravity worker cascade session that was spawned for a
    work order or mission where:
    1. The mission was a temporary test mission (e.g. summit-team-test-*),
    2. The mission is already terminal (COMPLETE, FAILED, CANCELLED) but the
       worker session has no correlated authoritative receipt, or
    3. The session was spawned dynamically without being formally bound to a live mission.
    """
    intents = load_wake_intents(intents_path)
    missions_path = missions_dir or (PROJECT_ROOT / "data" / "private" / "missions")
    orphans = []

    for it in intents:
        if it.get("wake_target") != "ANTIGRAVITY_WORKER":
            continue

        session_id = it.get("session_id")
        # The persistent default worker session is not an orphan
        if not session_id or session_id in (DEFAULT_WORKER_CONVERSATION_ID, PERSISTENT_DEFAULT_WORKER_ID):
            continue

        work_order_id = it.get("work_order_id") or ""
        mission_id = it.get("mission_id") or ""
        if not mission_id and work_order_id.startswith("mission-"):
            parts = work_order_id[len("mission-"):].split("-step-")
            if len(parts) > 1:
                mission_id = parts[0]

        is_orphan = False
        orphan_reason = ""

        # Check 1: Test missions (e.g. repeated generic Summit test missions)
        if "test" in mission_id.lower() or "test" in work_order_id.lower() or "summit-team-test" in work_order_id:
            is_orphan = True
            orphan_reason = "SPAWNED_BY_TEST_EXECUTION"

        # Check 2: Terminal mission without authoritative receipt
        elif mission_id:
            m_file = missions_path / f"{mission_id}.json"
            if not m_file.exists():
                is_orphan = True
                orphan_reason = "MISSION_FILE_NOT_FOUND"
            else:
                try:
                    m_data = json.loads(m_file.read_text(encoding="utf-8"))
                    m_status = m_data.get("status")
                    if m_status in ("COMPLETE", "COMPLETED", "FAILED", "CANCELLED"):
                        if not it.get("receipt_id"):
                            is_orphan = True
                            orphan_reason = f"MISSION_TERMINAL_{m_status}_WITHOUT_RECEIPT"
                except Exception:
                    pass

        # Check 3: Session without mission or receipt
        elif not mission_id and not it.get("receipt_id"):
            is_orphan = True
            orphan_reason = "ORPHAN_WITHOUT_MISSION_OR_RECEIPT"

        if is_orphan:
            orphans.append({
                "session_id": session_id,
                "work_order_id": work_order_id,
                "mission_id": mission_id,
                "attempt_id": it.get("wake_attempt_id"),
                "attempted_at": it.get("attempted_at"),
                "orphan_reason": orphan_reason,
                "already_reconciled": it.get("reconciliation_status") == "ORPHAN_PRESERVED",
            })

    return orphans


def reconcile_orphan_sessions(
    intents_path: Optional[Path] = None,
    missions_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Safely reconcile orphan sessions without terminating them.

    Marks orphan records in wake intents with 'reconciliation_status': 'ORPHAN_PRESERVED'.
    Preserves all existing data, history, and receipts intact.
    Does NOT terminate or cancel sessions on the Language Server.
    """
    intents = load_wake_intents(intents_path)
    orphans = detect_orphan_sessions(intents_path, missions_dir)
    orphan_session_ids = {o["session_id"] for o in orphans if o.get("session_id")}

    reconciled_count = 0
    now_str = _utc_now_iso()

    for it in intents:
        if it.get("wake_target") == "ANTIGRAVITY_WORKER" and it.get("session_id") in orphan_session_ids:
            if it.get("reconciliation_status") != "ORPHAN_PRESERVED":
                it["reconciliation_status"] = "ORPHAN_PRESERVED"
                it["reconciled_at"] = now_str
                reconciled_count += 1

    save_wake_intents(intents, intents_path)
    return {
        "total_orphans_detected": len(orphans),
        "newly_reconciled": reconciled_count,
        "orphan_sessions": orphans,
    }


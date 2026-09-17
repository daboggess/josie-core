#!/usr/bin/env python3
"""Automated qualification and verification test suite for Antigravity OpenAI Bridge.

Executes tests against the running bridge server:
1. Health check (GET /health)
2. Model discovery (GET /v1/models) - must contain exactly the two models
3. Model rejection for unauthorized model (POST /v1/chat/completions)
4. Non-streaming acceptance task (POST /v1/chat/completions)
5. Streaming chat completion (POST /v1/chat/completions with stream=true)
6. Pro model completion (POST /v1/chat/completions with josie-antigravity-pro)
7. Concurrency busy rejection (HTTP 429)
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import subprocess
import threading
import sys


BRIDGE_BASE_URL = "http://127.0.0.1:8792"
OPEN_WEBUI_BASE_URL = "http://127.0.0.1:3000"
ACCEPTANCE_TASK = "Read D:\\Josie\\AGENTS.md and report the operating-contract version and the active Josie root. Do not modify files."


def http_get(path: str) -> tuple[int, dict]:
    url = f"{BRIDGE_BASE_URL}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode("utf-8"))
        return e.code, data


def http_post_json(path: str, payload: dict, timeout: int = 120, headers: dict | None = None) -> tuple[int, dict]:
    url = f"{BRIDGE_BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode("utf-8"))
        return e.code, data


def http_post_sse(path: str, payload: dict, timeout: int = 120, headers: dict | None = None) -> tuple[int, list[str]]:
    url = f"{BRIDGE_BASE_URL}{path}"
    payload["stream"] = True
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    chunks = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if line:
                    chunks.append(line)
        return status, chunks
    except urllib.error.HTTPError as e:
        return e.code, [e.read().decode("utf-8", "replace")]


def get_active_agy_pids() -> set[str]:
    """Return the set of active agy.exe process IDs."""
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq agy.exe"], capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        if line.startswith("agy.exe"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                pids.add(parts[1])
    return pids


def get_open_webui_auth_token() -> str:
    """Retrieve auth token for Dustin Boggess from container."""
    res = subprocess.run(["docker", "exec", "josie-open-webui-1", "cat", "/proc/1/environ"], capture_output=True)
    secret = ""
    for entry in res.stdout.split(b"\x00"):
        if entry.startswith(b"WEBUI_SECRET_KEY="):
            secret = entry.decode("utf-8").split("=", 1)[1]
            break
    if not secret:
        raise RuntimeError("WEBUI_SECRET_KEY not found in container environment")

    admin_id = "9e6567cf-a372-44dd-8e30-688eb9383eeb"
    py_code = f"from open_webui.utils.auth import create_token; print(create_token(dict(id='{admin_id}')))"
    cmd = [
        "docker", "exec", "-e", f"WEBUI_SECRET_KEY={secret}", "josie-open-webui-1",
        "python", "-c", py_code
    ]
    res2 = subprocess.run(cmd, capture_output=True, text=True)
    for line in res2.stdout.splitlines():
        line = line.strip()
        if line.startswith("eyJ"):
            return line
    raise RuntimeError(f"Could not generate Open WebUI token: {res2.stderr}")


def open_webui_post_sse(path: str, payload: dict, token: str, timeout: int = 30) -> tuple[int, list[str]]:
    url = f"{OPEN_WEBUI_BASE_URL}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST"
    )
    chunks = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.status
        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").strip()
            if line:
                chunks.append(line)
    return status, chunks


def check_open_webui_last_message() -> dict:
    cmd = [
        "docker", "exec", "josie-open-webui-1",
        "python", "-c",
        "import sqlite3, json; con = sqlite3.connect('/app/backend/data/webui.db'); "
        "r = con.execute('SELECT id, role, done, error FROM chat_message WHERE role=\"assistant\" ORDER BY created_at DESC LIMIT 1').fetchone(); "
        "print(json.dumps({'id': r[0], 'role': r[1], 'done': r[2], 'error': r[3]}))"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(res.stdout.strip())


def test_health() -> bool:
    print("Test 1: Health check GET /health...")
    status, data = http_get("/health")
    assert status == 200, f"Expected 200, got {status}"
    assert data.get("status") == "ok", f"Expected status ok, got {data}"
    assert data.get("binding") == "127.0.0.1:8792", f"Unexpected binding: {data.get('binding')}"
    print("  PASS: Health check OK:", data)
    return True


def test_models() -> list[str]:
    print("Test 2: GET /v1/models...")
    status, data = http_get("/v1/models")
    assert status == 200, f"Expected 200, got {status}"
    assert data.get("object") == "list", f"Expected object=list, got {data}"
    model_ids = [m["id"] for m in data.get("data", [])]
    expected_ids = ["josie-antigravity-flash", "josie-antigravity-pro"]
    assert set(model_ids) == set(expected_ids), f"Expected exact models {expected_ids}, got {model_ids}"
    assert len(model_ids) == 2, f"Expected exactly 2 models, got {len(model_ids)}"
    print("  PASS: Exactly the 2 Josie Antigravity models returned:", model_ids)
    return model_ids


def test_invalid_model() -> bool:
    print("Test 3: Reject unsupported arbitrary model...")
    status, data = http_post_json("/v1/chat/completions", {
        "model": "arbitrary-gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert status == 400, f"Expected 400, got {status}"
    assert data.get("error", {}).get("code") == "model_not_found"
    print("  PASS: Rejected unsupported model with 400:", data["error"]["message"])
    return True


def test_acceptance_task() -> dict:
    print(f"Test 4: Acceptance task on josie-antigravity-flash:\n  Query: {ACCEPTANCE_TASK}")
    t0 = time.time()
    status, data = http_post_json("/v1/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": ACCEPTANCE_TASK}],
    }, timeout=120)
    duration = time.time() - t0
    assert status == 200, f"Expected 200, got {status}: {data}"
    assert data.get("object") == "chat.completion"
    assert data.get("model") == "josie-antigravity-flash"
    choices = data.get("choices", [])
    assert len(choices) > 0, "No choices returned"
    content = choices[0].get("message", {}).get("content", "")
    assert len(content) > 0, "Empty content returned"
    
    print(f"  Duration: {duration:.2f}s")
    print("  Response Content:\n" + ("-" * 40))
    print(content)
    print("-" * 40)
    
    # Verify required facts in acceptance response
    assert "0.1" in content, f"Expected version 0.1 in response: {content}"
    assert ("D:\\Josie" in content or "D:/Josie" in content), f"Expected active root D:\\Josie in response: {content}"
    
    usage = data.get("usage", {})
    print(f"  Usage: {usage}")
    print("  PASS: Acceptance criteria verified.")
    return {
        "content": content,
        "usage": usage,
        "id": data.get("id"),
        "duration_seconds": duration,
    }


def test_streaming() -> dict:
    print("Test 5: Streaming completion with stream=true...")
    status, chunks = http_post_sse("/v1/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "State the current operating status in exactly 3 words."}],
    }, timeout=60)
    assert status == 200, f"Expected 200, got {status}"
    assert len(chunks) > 0, "No chunks received"
    assert chunks[-1] == "data: [DONE]", f"Expected last chunk data: [DONE], got {chunks[-1]}"
    
    received_text = []
    for chunk in chunks:
        if chunk.startswith("data: ") and chunk != "data: [DONE]":
            chunk_data = json.loads(chunk[6:])
            choices = chunk_data.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    received_text.append(content)
    full_text = "".join(received_text)
    print(f"  Streamed {len(chunks)} chunks, full response: {full_text.strip()}")
    print("  PASS: Streaming verified.")
    return {"full_text": full_text.strip(), "chunk_count": len(chunks)}


def test_pro_model() -> dict:
    print("Test 6: Completion with josie-antigravity-pro...")
    t0 = time.time()
    status, data = http_post_json("/v1/chat/completions", {
        "model": "josie-antigravity-pro",
        "messages": [{"role": "user", "content": "Respond with the word PRO_VERIFIED"}],
    }, timeout=90)
    duration = time.time() - t0
    assert status == 200, f"Expected 200, got {status}: {data}"
    content = data["choices"][0]["message"]["content"]
    assert "PRO_VERIFIED" in content, f"Expected PRO_VERIFIED, got {content}"
    print(f"  Duration: {duration:.2f}s, Response: {content.strip()}")
    print("  PASS: Pro model verified.")
    return {"content": content.strip(), "duration_seconds": duration}


def test_concurrency_lock() -> bool:
    print("Test 7: Concurrency lock (busy rejection)...")
    busy_code = [None]
    busy_resp = [None]

    def long_request():
        http_post_json("/v1/chat/completions", {
            "model": "josie-antigravity-flash",
            "messages": [{"role": "user", "content": "Explain the difference between TCP and UDP in two paragraphs."}],
        }, timeout=120)

    def quick_second_request():
        time.sleep(0.5)  # Wait for first request to acquire the lock
        code, resp = http_post_json("/v1/chat/completions", {
            "model": "josie-antigravity-flash",
            "messages": [{"role": "user", "content": "Hello"}],
        }, timeout=10)
        busy_code[0] = code
        busy_resp[0] = resp

    t1 = threading.Thread(target=long_request)
    t2 = threading.Thread(target=quick_second_request)
    t1.start()
    t2.start()
    t2.join()
    t1.join()

    assert busy_code[0] == 429, f"Expected 429 for concurrent request, got {busy_code[0]}: {busy_resp[0]}"
    print("  PASS: Concurrent request rejected with 429 busy:", busy_resp[0]["error"]["message"])
    return True


def test_forced_timeout_and_done() -> dict:
    """Acceptance Criteria 2 & 3: Forced timeout produces terminal OpenAI SSE failure and ends with data: [DONE]."""
    print("Test 8: Forced timeout produces terminal OpenAI SSE failure and ends with data: [DONE]...")
    t0 = time.time()
    status, chunks = http_post_sse("/v1/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "Count from 1 to 1000 in full descriptive sentences."}],
        "timeout": 1,
    }, timeout=15)
    dur = time.time() - t0
    assert status == 200, f"Expected 200, got {status}"
    assert dur < 10, f"Forced timeout took unexpectedly long: {dur:.2f}s"
    assert len(chunks) >= 2, f"Expected at least 2 chunks, got {len(chunks)}: {chunks}"
    assert chunks[-1] == "data: [DONE]", f"Failed stream MUST end with 'data: [DONE]', got '{chunks[-1]}'"

    error_obj = None
    for chunk in chunks:
        if chunk.startswith("data: ") and chunk != "data: [DONE]":
            try:
                parsed = json.loads(chunk[6:])
                if "error" in parsed:
                    error_obj = parsed
            except Exception:
                pass

    assert error_obj is not None, f"No OpenAI error chunk found in stream: {chunks}"
    err = error_obj["error"]
    assert "message" in err and len(err["message"]) > 0, f"Missing error message: {err}"
    assert err.get("type") == "timeout_error", f"Expected type timeout_error, got {err.get('type')}"
    assert err.get("code") == "timeout", f"Expected code timeout, got {err.get('code')}"
    print(f"  PASS: Bounded timeout triggered in {dur:.2f}s")
    print(f"  PASS: Terminal SSE error event: {error_obj}")
    print(f"  PASS: Stream cleanly terminated with {chunks[-1]}")
    return {"error": err, "duration": dur, "chunks": chunks}


def test_child_process_cleanup() -> bool:
    """Acceptance Criterion 4: Child processes are cleaned up."""
    print("Test 9: Child process tree cleanup after forced timeout...")
    pids_before = get_active_agy_pids()

    # Execute a forced timeout job that spawns agy.exe
    status, chunks = http_post_sse("/v1/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "Explain particle physics in 5000 lines."}],
        "timeout": 1,
    }, timeout=15)
    assert status == 200
    assert chunks[-1] == "data: [DONE]"

    time.sleep(1.0)
    pids_after = get_active_agy_pids()
    leaked = pids_after - pids_before

    assert len(leaked) == 0, f"Leaked agy process PIDs detected: {leaked}"
    print(f"  PASS: Zero child processes leaked (Standing PIDs before: {pids_before}, after: {pids_after})")
    return True


def test_lock_released_and_immediate_followup() -> dict:
    """Acceptance Criteria 5 & 6: Concurrency lock is released and new request succeeds immediately."""
    print("Test 10: Concurrency lock release and immediate follow-up request...")
    # 1. Trigger a forced failure
    status1, chunks1 = http_post_sse("/v1/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "Fail fast"}],
        "simulate_failure": "crash",
    }, timeout=10)
    assert status1 == 200
    assert chunks1[-1] == "data: [DONE]"

    # 2. Immediately send follow-up request — must NOT receive 429 busy lock
    t0 = time.time()
    status2, data2 = http_post_json("/v1/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "Respond with the word LOCK_RELEASED_VERIFIED"}],
    }, timeout=30)
    dur = time.time() - t0
    assert status2 == 200, f"Expected 200 for immediate follow-up, got {status2}: {data2}"
    content = data2["choices"][0]["message"]["content"]
    assert "LOCK_RELEASED_VERIFIED" in content, f"Expected LOCK_RELEASED_VERIFIED, got {content}"
    print(f"  PASS: Lock released cleanly; immediate follow-up succeeded in {dur:.2f}s with: '{content.strip()}'")
    return {"content": content.strip(), "duration": dur}


def test_simulated_conditions() -> bool:
    """Extra verification: Mid-stream timeout, mid-stream crash, and nonzero exit."""
    print("Test 11: Simulated failure modes (crash, nonzero, midstream)...")
    sims = [
        ("Pre-stream Crash", "crash"),
        ("Pre-stream Nonzero", "nonzero"),
        ("Mid-stream Timeout", "midstream_timeout"),
        ("Mid-stream Crash", "midstream_crash"),
    ]
    for name, sim in sims:
        status, chunks = http_post_sse("/v1/chat/completions", {
            "model": "josie-antigravity-flash",
            "messages": [{"role": "user", "content": "Test simulation"}],
            "simulate_failure": sim,
        }, timeout=30)
        assert status == 200, f"{name}: Expected 200, got {status}"
        assert len(chunks) >= 2, f"{name}: Expected at least 2 chunks, got {chunks}"
        assert chunks[-1] == "data: [DONE]", f"{name}: Expected [DONE], got {chunks[-1]}"
        assert any("error" in c.lower() for c in chunks), f"{name}: Expected error chunk in {chunks}"
        print(f"  PASS: {name} ({sim}) terminated with terminal error and [DONE]")
    return True


def test_real_open_webui_streaming() -> dict:
    """Acceptance Criterion 10: Real Open WebUI streaming request does not hang frontend indefinitely on timeout."""
    print("Test 12: Real Open WebUI streaming failure behavior...")
    token = get_open_webui_auth_token()
    assert token, "Failed to get Open WebUI token"

    # Step A: Test forced timeout streaming through Open WebUI
    t0 = time.time()
    status, chunks = open_webui_post_sse("/api/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "Count from 1 to 1000 in full sentences."}],
        "stream": True,
        "timeout": 1,
    }, token=token, timeout=15)
    dur = time.time() - t0

    assert dur < 10, f"Open WebUI hung too long on timeout: {dur:.2f}s"
    assert status == 200, f"Expected 200 from Open WebUI, got {status}"
    assert len(chunks) >= 2, f"Expected chunks from Open WebUI, got {chunks}"
    assert chunks[-1] == "data: [DONE]", f"Open WebUI stream did not terminate with [DONE]: {chunks[-1]}"

    has_error = any("error" in c.lower() for c in chunks)
    assert has_error, f"Expected error event in Open WebUI stream: {chunks}"
    print(f"  PASS: Open WebUI timeout stream terminated in {dur:.2f}s with terminal data: [DONE]")

    # Step B: Check Open WebUI DB to prove message was marked done (not stuck spinning)
    msg_state = check_open_webui_last_message()
    assert msg_state.get("done") == 1, f"Open WebUI message was left stuck with done={msg_state.get('done')}"
    print(f"  PASS: Open WebUI DB assistant message marked done=1: {msg_state}")

    # Step C: Immediate follow-up request through Open WebUI succeeds
    t0_succ = time.time()
    succ_status, succ_chunks = open_webui_post_sse("/api/chat/completions", {
        "model": "josie-antigravity-flash",
        "messages": [{"role": "user", "content": "Respond with OW_RECOVERED_OK"}],
        "stream": True,
    }, token=token, timeout=30)
    succ_dur = time.time() - t0_succ
    assert succ_status == 200, f"Expected 200 on follow-up, got {succ_status}"
    assert succ_chunks[-1] == "data: [DONE]"
    print(f"  PASS: Open WebUI immediate follow-up completed in {succ_dur:.2f}s")
    return {"timeout_duration": dur, "followup_duration": succ_dur, "chunks": chunks}


def run_all_tests():
    print("=" * 70)
    print("RUNNING ANTIGRAVITY OPENAI BRIDGE QUALIFICATION SUITE")
    print("=" * 70)
    test_health()
    test_models()
    test_invalid_model()
    acceptance_res = test_acceptance_task()
    streaming_res = test_streaming()
    pro_res = test_pro_model()
    test_concurrency_lock()
    timeout_res = test_forced_timeout_and_done()
    test_child_process_cleanup()
    followup_res = test_lock_released_and_immediate_followup()
    test_simulated_conditions()
    ow_res = test_real_open_webui_streaming()
    print("=" * 70)
    print("ALL 10 ACCEPTANCE CRITERIA SUCCESSFULLY PROVED AND QUALIFIED!")
    print("=" * 70)
    return {
        "acceptance": acceptance_res,
        "streaming": streaming_res,
        "pro": pro_res,
        "timeout": timeout_res,
        "followup": followup_res,
        "open_webui": ow_res,
    }


if __name__ == "__main__":
    run_all_tests()

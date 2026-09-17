#!/usr/bin/env python3
"""Antigravity-to-Open-WebUI Bridge for Josie.

Exposes an OpenAI-compatible API (GET /v1/models, POST /v1/chat/completions)
backed by the official Antigravity CLI (`agy`) on Windows, authenticated via
the host's existing Google AI Pro account.

Constraints & Security:
- Root / working directory is locked to D:\\Josie. Arbitrary cwd is forbidden.
- Only official agy executable is invoked.
- Arbitrary models are forbidden. Exposes:
    josie-antigravity-flash -> gemini-3.8-flash-high
    josie-antigravity-pro   -> gemini-3.1-pro-high
- Concurrency limit is strictly 1. Busy requests receive HTTP 429.
- Paid APIs and credit fallback are strictly forbidden; environment is scrubbed.
- Never uses --dangerously-skip-permissions.
- Bounded execution timeout and bounded conversation context extraction.
- Binds strictly to 127.0.0.1:8792 (reachable by Docker via host.docker.internal).
"""

from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import uuid

# Configuration constants
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8792
DEFAULT_TIMEOUT_SECONDS = 180
MAX_PROMPT_CHARS = 8000
MAX_SYSTEM_CHARS = 2000
MAX_HISTORY_CHARS = 2000

CANONICAL_WORKSPACE = Path(r"D:\Josie").resolve()

MODEL_MAPPINGS = {
    "josie-antigravity-flash": "gemini-3.8-flash-high",
    "josie-antigravity-pro": "gemini-3.1-pro-high",
}

# Environment variables to remove so paid credentials or unintended keys cannot be used
STRIPPED_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPENAI_ORG_ID",
    "OPENAI_PROJECT_ID",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GEMINI_CLI_USE_COMPUTE_ADC",
    "ANTHROPIC_API_KEY",
    "CLOUD_SHELL",
    "GOOGLE_GEMINI_BASE_URL",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_PROJECT_ID",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_GENAI_USE_GCA",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("antigravity-bridge")

_job_lock = threading.Lock()
_active_proc_lock = threading.Lock()
_active_proc: subprocess.Popen | None = None


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and any child processes in its tree."""
    if proc.poll() is not None:
        return
    pid = proc.pid
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        else:
            proc.kill()
    except Exception as e:
        logger.warning("Error terminating process tree for PID %d: %s", pid, e)
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=2)
    except Exception:
        pass


def _set_active_proc(proc: subprocess.Popen | None) -> None:
    global _active_proc
    with _active_proc_lock:
        _active_proc = proc


def cleanup_active_proc() -> None:
    global _active_proc
    with _active_proc_lock:
        if _active_proc is not None:
            try:
                kill_process_tree(_active_proc)
            except Exception:
                pass
            _active_proc = None


atexit.register(cleanup_active_proc)


def find_agy_binary() -> str:
    """Locate the official agy executable."""
    candidate = Path(os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"))
    if candidate.is_file():
        return str(candidate)
    
    which_path = shutil.which("agy.exe") or shutil.which("agy")
    if which_path and os.path.isfile(which_path):
        return which_path
    
    raise FileNotFoundError("Official Antigravity CLI executable 'agy' not found.")


def extract_text_content(content: Any) -> str:
    """Extract plain text from Open WebUI / OpenAI message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def render_bounded_prompt(messages: list[dict[str, Any]]) -> str:
    """Extract bounded task-relevant context for Antigravity.
    
    Favors the most recent user task plus only the minimum necessary context.
    Does NOT blindly concatenate entire conversation history.
    """
    if not messages:
        return ""

    # Find the latest user message
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break

    if last_user_idx == -1:
        # Fallback to the last message if no user role found
        last_user_idx = len(messages) - 1

    last_user_content = extract_text_content(messages[last_user_idx].get("content", ""))

    # Check for system instructions
    system_text = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_text = extract_text_content(msg.get("content", ""))[:MAX_SYSTEM_CHARS].strip()
            break

    # Check for immediate previous assistant context (if preceding turns exist)
    previous_assistant_text = ""
    if last_user_idx > 0:
        for i in range(last_user_idx - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                previous_assistant_text = extract_text_content(messages[i].get("content", ""))[:MAX_HISTORY_CHARS].strip()
                break

    # If this is a standalone prompt with no system instructions or previous context,
    # pass the user task directly.
    if not system_text and not previous_assistant_text:
        return last_user_content[:MAX_PROMPT_CHARS]

    blocks: list[str] = []
    if system_text:
        blocks.append(f"[System Instructions]\n{system_text}")
    if previous_assistant_text:
        blocks.append(f"[Previous Context]\nAssistant: {previous_assistant_text}")
    blocks.append(f"[Current Task]\n{last_user_content}")

    combined = "\n\n".join(blocks)
    if len(combined) > MAX_PROMPT_CHARS:
        return combined[:MAX_PROMPT_CHARS]
    return combined


def execute_antigravity_stream(
    prompt: str,
    model_slug: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    simulate_failure: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Execute agy in stream-json mode and yield parsed NDJSON events."""
    if simulate_failure == "timeout":
        time.sleep(0.1)
        raise TimeoutError(f"Antigravity job timed out after {timeout_seconds}s")
    if simulate_failure == "crash":
        raise RuntimeError("Antigravity process crashed unexpectedly")
    if simulate_failure == "nonzero":
        raise RuntimeError("agy exited with code 1: Simulated fatal execution error")
    if simulate_failure == "midstream_timeout":
        time.sleep(0.05)
        yield {"event": "step_update", "step_update": {"text_delta": "Partial output before timeout..."}}
        time.sleep(0.05)
        raise TimeoutError(f"Antigravity job timed out after {timeout_seconds}s (mid-stream)")
    if simulate_failure == "midstream_crash":
        time.sleep(0.05)
        yield {"event": "step_update", "step_update": {"text_delta": "Partial output before crash..."}}
        time.sleep(0.05)
        raise RuntimeError("Antigravity process crashed mid-stream")

    agy_exe = find_agy_binary()

    # Build clean environment scrubbed of paid keys
    env = os.environ.copy()
    for var in STRIPPED_ENV_VARS:
        env.pop(var, None)

    cmd = [
        agy_exe,
        "-p",
        prompt,
        "--model",
        model_slug,
        "--output-format",
        "stream-json",
        "--disable-slash-commands",
        "--print-timeout",
        f"{timeout_seconds}s",
    ]

    logger.info("Executing Antigravity: model=%s, cwd=%s, timeout=%ds", model_slug, CANONICAL_WORKSPACE, timeout_seconds)

    proc = subprocess.Popen(
        cmd,
        cwd=str(CANONICAL_WORKSPACE),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    _set_active_proc(proc)

    q: queue.Queue[tuple[str, Any]] = queue.Queue()
    stderr_lines: list[str] = []

    def _stdout_reader(pipe: Any) -> None:
        try:
            for line in iter(pipe.readline, ""):
                q.put(("line", line))
        except Exception as e:
            q.put(("error", e))
        finally:
            try:
                pipe.close()
            except Exception:
                pass
            q.put(("eof", None))

    def _stderr_reader(pipe: Any) -> None:
        try:
            for line in iter(pipe.readline, ""):
                stderr_lines.append(line)
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    stdout_thread = threading.Thread(target=_stdout_reader, args=(proc.stdout,), daemon=True)
    stderr_thread = threading.Thread(target=_stderr_reader, args=(proc.stderr,), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    start_time = time.time()
    had_success_result = False

    try:
        while True:
            elapsed = time.time() - start_time
            remaining = timeout_seconds - elapsed
            if remaining <= 0:
                kill_process_tree(proc)
                raise TimeoutError(f"Antigravity job timed out after {timeout_seconds}s")

            try:
                msg_type, val = q.get(timeout=min(max(remaining, 0.05), 0.2))
            except queue.Empty:
                if proc.poll() is not None and q.empty():
                    break
                continue

            if msg_type == "eof":
                break
            elif msg_type == "error":
                raise val
            elif msg_type == "line":
                line_str = val.strip()
                if not line_str:
                    continue

                try:
                    event = json.loads(line_str)
                    if event.get("event") == "result":
                        res = event.get("result", {})
                        if res.get("status") == "SUCCESS":
                            had_success_result = True
                    yield event

                except json.JSONDecodeError:
                    logger.warning("Unparseable agy stdout line: %s", line_str[:120])

        proc.wait(timeout=5)
        if proc.returncode != 0 and not had_success_result:
            stderr_out = "".join(stderr_lines).strip()
            raise RuntimeError(f"agy exited with code {proc.returncode}: {stderr_out}")

    finally:
        kill_process_tree(proc)
        _set_active_proc(None)


class AntigravityBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        try:
            payload = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.info("Client disconnected before JSON response could be delivered.")

    def _send_error(self, status: int, message: str, err_type: str = "invalid_request_error", code: str | None = None) -> None:
        self._send_json(
            status,
            {
                "error": {
                    "message": message,
                    "type": err_type,
                    "param": None,
                    "code": code or str(status),
                }
            },
        )

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/health", "/v1/health", ""):
            try:
                agy_path = find_agy_binary()
                agy_ok = True
            except Exception:
                agy_path = ""
                agy_ok = False

            self._send_json(
                200,
                {
                    "status": "ok" if agy_ok else "degraded",
                    "service": "antigravity-openai-bridge",
                    "version": "1.0.0",
                    "binding": f"{DEFAULT_HOST}:{DEFAULT_PORT}",
                    "workspace": str(CANONICAL_WORKSPACE),
                    "agy_executable": agy_path,
                    "models": list(MODEL_MAPPINGS.keys()),
                },
            )
            return

        if path in ("/v1/models", "/models"):
            created_ts = int(time.time())
            models_data = [
                {
                    "id": model_id,
                    "object": "model",
                    "created": created_ts,
                    "owned_by": "josie-antigravity",
                    "permission": [],
                    "root": model_id,
                    "parent": None,
                }
                for model_id in MODEL_MAPPINGS
            ]
            self._send_json(200, {"object": "list", "data": models_data})
            return

        self._send_error(404, f"Path '{self.path}' not found", "not_found_error", "not_found")

    def do_POST(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/v1/chat/completions", "/chat/completions"):
            self._send_error(404, f"Endpoint '{self.path}' not found", "not_found_error", "not_found")
            return

        # Read request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_error(400, "Empty request body", "invalid_request_error", "empty_body")
                return
            body_bytes = self.rfile.read(content_length)
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            self._send_error(400, f"Malformed JSON request: {e}", "invalid_request_error", "invalid_json")
            return

        # Model validation
        requested_model = body.get("model", "")
        if requested_model not in MODEL_MAPPINGS:
            supported = ", ".join(MODEL_MAPPINGS.keys())
            self._send_error(
                400,
                f"Model '{requested_model}' is not supported. Supported models: {supported}",
                "invalid_request_error",
                "model_not_found",
            )
            return

        target_slug = MODEL_MAPPINGS[requested_model]
        stream_requested = bool(body.get("stream", False))

        # Enforce concurrency limit = 1
        acquired = _job_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("Rejecting request: Bridge is currently busy with another job")
            self._send_error(
                429,
                "Antigravity bridge is busy processing another job. Only one concurrent job is allowed.",
                "server_busy",
                "busy",
            )
            return

        try:
            messages = body.get("messages", [])
            rendered_prompt = render_bounded_prompt(messages)
            if not rendered_prompt:
                self._send_error(400, "No valid user message found in conversation", "invalid_request_error", "empty_prompt")
                return

            completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            created_ts = int(time.time())

            # Bounded execution timeout extraction
            request_timeout = DEFAULT_TIMEOUT_SECONDS
            raw_timeout = body.get("timeout") or self.headers.get("X-Bridge-Timeout")
            if raw_timeout is not None:
                try:
                    val = int(raw_timeout)
                    if 1 <= val <= 600:
                        request_timeout = val
                except (ValueError, TypeError):
                    pass

            simulate_failure = body.get("simulate_failure") or self.headers.get("X-Simulate-Failure")

            if stream_requested:
                self._handle_streaming_chat(
                    completion_id,
                    created_ts,
                    requested_model,
                    target_slug,
                    rendered_prompt,
                    timeout_seconds=request_timeout,
                    simulate_failure=simulate_failure,
                )
            else:
                self._handle_non_streaming_chat(
                    completion_id,
                    created_ts,
                    requested_model,
                    target_slug,
                    rendered_prompt,
                    timeout_seconds=request_timeout,
                    simulate_failure=simulate_failure,
                )

        except TimeoutError as e:
            logger.error("Job timed out: %s", e)
            self._send_error(504, str(e), "timeout_error", "timeout")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.info("Client connection aborted during request.")
        except Exception as e:
            logger.exception("Antigravity bridge error: %s", e)
            self._send_error(502, f"Antigravity execution failed: {e}", "antigravity_error", "execution_failed")
        finally:
            _job_lock.release()

    def _handle_non_streaming_chat(
        self,
        completion_id: str,
        created_ts: int,
        model_id: str,
        target_slug: str,
        prompt: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        simulate_failure: str | None = None,
    ) -> None:
        accumulated_text = []
        final_result: dict[str, Any] | None = None

        for event in execute_antigravity_stream(
            prompt,
            target_slug,
            timeout_seconds=timeout_seconds,
            simulate_failure=simulate_failure,
        ):
            ev_name = event.get("event")
            if ev_name == "step_update":
                step = event.get("step_update", {})
                delta = step.get("text_delta")
                if delta:
                    accumulated_text.append(delta)
            elif ev_name == "result":
                final_result = event.get("result")

        full_content = "".join(accumulated_text)
        usage_info = {}
        if final_result:
            if final_result.get("status") != "SUCCESS":
                err_status = final_result.get("status", "FAILED")
                err_msg = final_result.get("error", f"Antigravity returned status: {err_status}")
                raise RuntimeError(err_msg)
            if not full_content and final_result.get("response"):
                full_content = final_result.get("response", "")
            usage_info = final_result.get("usage", {})

        response_payload = {
            "id": completion_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": model_id,
            "system_fingerprint": "fp_josie_antigravity",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": full_content,
                    },
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage_info.get("input_tokens", 0),
                "completion_tokens": usage_info.get("output_tokens", 0),
                "total_tokens": usage_info.get("total_tokens", 0),
            },
        }

        self._send_json(200, response_payload)

    def _handle_streaming_chat(
        self,
        completion_id: str,
        created_ts: int,
        model_id: str,
        target_slug: str,
        prompt: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        simulate_failure: str | None = None,
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def write_sse_data(obj: Any) -> bool:
            try:
                if isinstance(obj, str):
                    line = f"data: {obj}\n\n"
                else:
                    line = f"data: {json.dumps(obj)}\n\n"
                raw = line.encode("utf-8")
                chunk = f"{len(raw):X}\r\n".encode("ascii") + raw + b"\r\n"
                self.wfile.write(chunk)
                self.wfile.flush()
                return True
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                logger.info("Client disconnected during SSE streaming.")
                return False

        def write_sse_error(message: str, err_type: str = "invalid_request_error", code: str | None = None) -> bool:
            err_payload = {
                "error": {
                    "message": message,
                    "type": err_type,
                    "param": None,
                    "code": code or "500",
                }
            }
            return write_sse_data(err_payload)

        # Initial role chunk
        initial_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_id,
            "system_fingerprint": "fp_josie_antigravity",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "logprobs": None,
                    "finish_reason": None,
                }
            ],
        }
        if not write_sse_data(initial_chunk):
            return

        accumulated_len = 0
        final_result: dict[str, Any] | None = None

        try:
            for event in execute_antigravity_stream(
                prompt,
                target_slug,
                timeout_seconds=timeout_seconds,
                simulate_failure=simulate_failure,
            ):
                ev_name = event.get("event")
                if ev_name == "step_update":
                    step = event.get("step_update", {})
                    delta = step.get("text_delta")
                    if delta:
                        accumulated_len += len(delta)
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model_id,
                            "system_fingerprint": "fp_josie_antigravity",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": delta},
                                    "logprobs": None,
                                    "finish_reason": None,
                                }
                            ],
                        }
                        if not write_sse_data(chunk):
                            return
                elif ev_name == "result":
                    final_result = event.get("result")

            if final_result:
                if final_result.get("status") != "SUCCESS":
                    err_status = final_result.get("status", "FAILED")
                    err_msg = final_result.get("error", f"Antigravity returned status: {err_status}")
                    raise RuntimeError(err_msg)

                result_resp = final_result.get("response", "")
                if len(result_resp) > accumulated_len:
                    remaining = result_resp[accumulated_len:]
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model_id,
                        "system_fingerprint": "fp_josie_antigravity",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": remaining},
                                "logprobs": None,
                                "finish_reason": None,
                            }
                        ],
                    }
                    if not write_sse_data(chunk):
                        return

            # Stop chunk
            stop_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model_id,
                "system_fingerprint": "fp_josie_antigravity",
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "logprobs": None,
                        "finish_reason": "stop",
                    }
                ],
            }
            write_sse_data(stop_chunk)

        except TimeoutError as e:
            logger.error("Job timed out during streaming: %s", e)
            write_sse_error(str(e), err_type="timeout_error", code="timeout")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.info("Client disconnected during stream execution.")
            return
        except Exception as e:
            logger.exception("Antigravity bridge stream error: %s", e)
            write_sse_error(f"Antigravity execution failed: {e}", err_type="antigravity_error", code="execution_failed")
        finally:
            write_sse_data("[DONE]")
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, AntigravityBridgeHandler)
    logger.info("Antigravity OpenAI Bridge listening on %s:%d (CWD=%s)", host, port, CANONICAL_WORKSPACE)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Antigravity OpenAI Bridge...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity OpenAI Bridge for Josie")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host address to bind (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port to bind (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    run_server(args.host, args.port)

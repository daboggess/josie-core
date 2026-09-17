"""Bounded, deterministic browser relay for Founding Summit exchanges.

Summit Relay v0.1 is deliberately only a communication wire.  It exposes a
loopback endpoint to a dedicated Chrome extension, builds attributed envelopes,
enforces the proposal/challenge/rebuttal bound, and writes append-only receipts.
It has no model, database, memory-promotion, or execution-routing authority.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


RELAY_VERSION = "0.1.0"
CONFIG_KEYS = {
    "schema_version",
    "relay_version",
    "enabled",
    "binding",
    "port",
    "max_payload_chars",
    "max_exchange_rounds",
    "action_timeout_seconds",
    "poll_interval_ms",
    "providers",
}
PROVIDER_KEYS = {"source", "url_patterns"}
WORKERS = {"sophie", "bernie", "josie"}
RESULT_KEYS = {
    "action_id",
    "ok",
    "assistant_text",
    "tab_id",
    "page_url",
    "page_title",
    "error_code",
    "error_detail",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean_text(value: object, *, label: str, maximum: int, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.replace("\x00", "").strip()
    if not empty and not text:
        raise ValueError(f"{label} is required")
    if len(text) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    return text


def load_relay_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "summit-relay.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Summit Relay configuration is missing or invalid") from exc
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise ValueError("Summit Relay configuration has unexpected fields")
    if config["schema_version"] != 1 or config["relay_version"] != RELAY_VERSION:
        raise ValueError("Summit Relay configuration version is unsupported")
    if config["enabled"] is not True:
        raise ValueError("Summit Relay is disabled")
    if config["binding"] != "127.0.0.1":
        raise ValueError("Summit Relay may bind only to loopback")
    integer_ranges = {
        "port": (1, 65535),
        "max_payload_chars": (512, 20_000),
        "max_exchange_rounds": (1, 3),
        "action_timeout_seconds": (30, 300),
        "poll_interval_ms": (500, 10_000),
    }
    for key, (minimum, maximum) in integer_ranges.items():
        value = config[key]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"Summit Relay {key} is invalid")
    if config["max_exchange_rounds"] != 3:
        raise ValueError("Summit Relay v0.1 requires exactly three bounded exchange rounds")
    providers = config["providers"]
    if not isinstance(providers, dict) or set(providers) != WORKERS:
        raise ValueError("Summit Relay must configure exactly Sophie, Bernie, and Josie")
    for worker, provider in providers.items():
        if not isinstance(provider, dict) or set(provider) != PROVIDER_KEYS:
            raise ValueError(f"Summit Relay provider {worker} is invalid")
        _clean_text(provider["source"], label=f"{worker} source", maximum=60)
        patterns = provider["url_patterns"]
        if not isinstance(patterns, list) or not patterns or not all(
            isinstance(item, str) and item.startswith(("https://", "http://localhost", "http://127.0.0.1"))
            for item in patterns
        ):
            raise ValueError(f"Summit Relay provider {worker} URL patterns are invalid")
    return config


def load_relay_token(project_root: Path) -> str:
    path = project_root / "data" / "private" / "summit-relay.token"
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("Summit Relay credential is missing") from exc
    if not 32 <= len(token) <= 200:
        raise ValueError("Summit Relay credential is invalid")
    return token


def format_envelope(
    *, from_worker: str, round_number: str, source: str, content: str,
    maximum: int, relay_instruction: str | None = None,
) -> str:
    body = _clean_text(content, label="Relay content", maximum=maximum)
    sender = _clean_text(from_worker, label="Relay sender", maximum=40).upper()
    origin = _clean_text(source, label="Relay source", maximum=80)
    round_text = _clean_text(round_number, label="Relay round", maximum=20)
    envelope = (
        f"FROM: {sender}\nVIA: JOSIE\nROUND: {round_text}\nSOURCE: {origin}\n\n"
        f"<BEGIN EXACT RELAY CONTENT>\n{body}\n<END EXACT RELAY CONTENT>"
    )
    if relay_instruction:
        instruction = _clean_text(
            relay_instruction, label="Relay instruction", maximum=500
        )
        envelope += f"\n\nRELAY INSTRUCTION (FROM SUMMIT RELAY, NOT DUSTIN):\n{instruction}"
    return envelope


class ReceiptLog:
    """Thread-safe append-only JSONL receipt writer."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, event: dict[str, Any]) -> None:
        record = {"timestamp": _utc_now(), **event}
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(encoded)
                handle.flush()


@dataclass
class RelayAction:
    action_id: str
    worker: str
    source: str
    round_number: str
    payload: str
    expected_exact: str | None
    timeout_seconds: int
    status: str = "queued"

    def public(self, patterns: list[str]) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "operation": "send_and_capture",
            "worker": self.worker,
            "source": self.source,
            "round": self.round_number,
            "payload": self.payload,
            "expected_exact": self.expected_exact,
            "timeout_seconds": self.timeout_seconds,
            "url_patterns": patterns,
        }


@dataclass
class AcceptanceRelay:
    config: dict[str, Any]
    receipts: ReceiptLog
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actions: list[RelayAction] = field(default_factory=list)
    captured: dict[str, str] = field(default_factory=dict)
    status: str = "running"
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        if self.actions:
            return
        maximum = self.config["max_payload_chars"]
        seed = format_envelope(
            from_worker="SUMMIT_RELAY",
            round_number="SETUP",
            source="local acceptance fixture",
            content="Create the harmless Sophie source message for this relay acceptance test.",
            maximum=maximum,
            relay_instruction=(
                "Respond with exactly: Sophie relay test: Please respond with exactly "
                "BERNIE_RELAY_OK. Do not add any other text."
            ),
        )
        self._queue("sophie", "1", seed, "Sophie relay test: Please respond with exactly BERNIE_RELAY_OK.")
        self.receipts.append({
            "event": "job_started", "job_id": self.job_id,
            "workflow": "harmless_acceptance", "max_exchange_rounds": 3,
            "production_action": False,
        })

    def _queue(
        self, worker: str, round_number: str, payload: str,
        expected_exact: str | None,
    ) -> None:
        if len(payload) > self.config["max_payload_chars"] + 1_000:
            raise ValueError("Attributed relay payload exceeds the configured bound")
        provider = self.config["providers"][worker]
        self.actions.append(RelayAction(
            action_id=str(uuid.uuid4()), worker=worker, source=provider["source"],
            round_number=round_number, payload=payload,
            expected_exact=expected_exact,
            timeout_seconds=self.config["action_timeout_seconds"],
        ))

    def next_action(self) -> dict[str, Any] | None:
        if self.status != "running":
            return None
        for action in self.actions:
            if action.status == "dispatched":
                return None
            if action.status == "queued":
                action.status = "dispatched"
                self.receipts.append({
                    "event": "send_dispatched", "job_id": self.job_id,
                    "action_id": action.action_id, "source_worker": "summit_relay",
                    "destination_worker": action.worker, "source": action.source,
                    "round": action.round_number, "payload_sha256": _sha256(action.payload),
                    "payload_chars": len(action.payload), "send_success": None,
                    "response_capture_success": None,
                })
                provider = self.config["providers"][action.worker]
                return action.public(provider["url_patterns"])
        return None

    def submit_result(self, payload: object) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) != RESULT_KEYS:
            raise ValueError("Relay result has unexpected fields")
        action_id = _clean_text(payload["action_id"], label="Action ID", maximum=80)
        matches = [item for item in self.actions if item.action_id == action_id]
        if len(matches) != 1 or matches[0].status != "dispatched":
            raise ValueError("Relay result does not match the active action")
        action = matches[0]
        ok = payload["ok"]
        if type(ok) is not bool:
            raise ValueError("Relay result status must be Boolean")
        tab_id = payload["tab_id"]
        if tab_id is not None and type(tab_id) is not int:
            raise ValueError("Relay tab ID is invalid")
        page_url = _clean_text(payload["page_url"], label="Page URL", maximum=2_000, empty=True)
        _clean_text(payload["page_title"], label="Page title", maximum=300, empty=True)
        conversation_ref = _sha256(page_url)[:24] if page_url else None
        if not ok:
            code = _clean_text(payload["error_code"], label="Error code", maximum=80)
            detail = _clean_text(payload["error_detail"], label="Error detail", maximum=500, empty=True)
            action.status = "failed"
            self._stop(f"{code}: {detail}".rstrip(": "), action=action,
                       tab_id=tab_id, conversation_ref=conversation_ref)
            return self.status_report()

        response = _clean_text(
            payload["assistant_text"], label="Assistant response",
            maximum=self.config["max_payload_chars"],
        )
        if action.expected_exact is not None and response != action.expected_exact:
            action.status = "failed"
            self.receipts.append({
                "event": "response_rejected", "job_id": self.job_id,
                "action_id": action.action_id, "source_worker": action.worker,
                "destination_worker": "summit_relay", "round": action.round_number,
                "tab_id": tab_id, "conversation_ref": conversation_ref,
                "payload_sha256": _sha256(response), "payload_chars": len(response),
                "send_success": True, "response_capture_success": True,
                "stop_reason": "expected_exact_mismatch",
            })
            self.status = "stopped"
            self.stop_reason = "expected_exact_mismatch"
            return self.status_report()

        action.status = "completed"
        self.receipts.append({
            "event": "response_captured", "job_id": self.job_id,
            "action_id": action.action_id, "source_worker": action.worker,
            "destination_worker": "summit_relay", "source": action.source,
            "round": action.round_number, "tab_id": tab_id,
            "conversation_ref": conversation_ref, "payload_sha256": _sha256(response),
            "payload_chars": len(response), "send_success": True,
            "response_capture_success": True,
        })
        self._advance(action, response)
        return self.status_report()

    def _advance(self, action: RelayAction, response: str) -> None:
        maximum = self.config["max_payload_chars"]
        if action.worker == "sophie" and action.round_number == "1":
            self.captured["sophie_proposal"] = response
            payload = format_envelope(
                from_worker="SOPHIE", round_number="1", source="ChatGPT",
                content=response, maximum=maximum,
            )
            self._queue("bernie", "2", payload, "BERNIE_RELAY_OK")
            return
        if action.worker == "bernie":
            self.captured["bernie_challenge"] = response
            payload = format_envelope(
                from_worker="BERNIE", round_number="2", source="Gemini",
                content=response, maximum=maximum,
                relay_instruction="Respond with exactly SOPHIE_RELAY_OK. Do not add any other text.",
            )
            self._queue("sophie", "3", payload, "SOPHIE_RELAY_OK")
            return
        if action.worker == "sophie" and action.round_number == "3":
            self.captured["sophie_rebuttal"] = response
            summary = (
                "TEAM ALIGNED\n"
                "Harmless Summit Relay v0.1 acceptance exchange completed.\n"
                "Sophie source: captured.\nBernie response: BERNIE_RELAY_OK.\n"
                "Sophie final response: SOPHIE_RELAY_OK.\n"
                f"Local receipt job ID: {self.job_id}."
            )
            payload = format_envelope(
                from_worker="SUMMIT_RELAY", round_number="RECEIPT",
                source="local deterministic receipt", content=summary, maximum=maximum,
                relay_instruction="Acknowledge this harmless local relay receipt briefly; do not execute tools or actions.",
            )
            self._queue("josie", "RECEIPT", payload, None)
            return
        if action.worker == "josie":
            self.captured["josie_receipt"] = response
            self.status = "completed"
            self.stop_reason = "bounded_exchange_complete"
            self.receipts.append({
                "event": "job_completed", "job_id": self.job_id,
                "result": "TEAM ALIGNED", "stop_reason": self.stop_reason,
                "exchange_rounds": 3, "messages_sent": 4,
                "production_action": False,
            })
            return
        raise ValueError("Relay action sequence is invalid")

    def _stop(
        self, reason: str, *, action: RelayAction,
        tab_id: int | None, conversation_ref: str | None,
    ) -> None:
        self.status = "stopped"
        self.stop_reason = reason
        self.receipts.append({
            "event": "job_stopped", "job_id": self.job_id,
            "action_id": action.action_id, "source_worker": "summit_relay",
            "destination_worker": action.worker, "round": action.round_number,
            "tab_id": tab_id, "conversation_ref": conversation_ref,
            "send_success": False, "response_capture_success": False,
            "stop_reason": reason,
        })

    def status_report(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "completed_actions": sum(item.status == "completed" for item in self.actions),
            "queued_actions": sum(item.status == "queued" for item in self.actions),
            "captured_workers": sorted(self.captured),
        }


class RelayController:
    def __init__(self, config: dict[str, Any], receipts: ReceiptLog, *, acceptance: bool):
        self.config = config
        self.receipts = receipts
        self.job = AcceptanceRelay(config, receipts) if acceptance else None
        self._lock = threading.Lock()

    def next_action(self) -> dict[str, Any] | None:
        with self._lock:
            return self.job.next_action() if self.job else None

    def submit_result(self, payload: object) -> dict[str, Any]:
        with self._lock:
            if not self.job:
                raise ValueError("No relay job is active")
            return self.job.submit_result(payload)

    def status(self) -> dict[str, Any]:
        with self._lock:
            if not self.job:
                return {"status": "idle", "relay_version": RELAY_VERSION}
            return {"relay_version": RELAY_VERSION, **self.job.status_report()}


def _valid_extension_origin(origin: str | None) -> bool:
    return bool(origin and origin.startswith("chrome-extension://") and len(origin) <= 100)


def make_relay_handler(
    *, controller: RelayController, token: str,
) -> type[BaseHTTPRequestHandler]:
    contact_stats = {"extension_contacts": 0, "authorized_contacts": 0, "rejected_contacts": 0}
    contact_lock = threading.Lock()

    class SummitRelayHandler(BaseHTTPRequestHandler):
        server_version = "JosieSummitRelay/0.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, status: HTTPStatus, body: dict[str, Any], *, cors: bool = False) -> None:
            encoded = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if cors:
                origin = self.headers.get("Origin")
                if _valid_extension_origin(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(encoded)

        def _authorized(self) -> bool:
            supplied = self.headers.get("X-Josie-Summit-Token", "")
            return hmac.compare_digest(supplied, token)

        def do_OPTIONS(self) -> None:
            origin = self.headers.get("Origin")
            if self.path not in {"/next", "/result"} or not _valid_extension_origin(origin):
                self._send(HTTPStatus.FORBIDDEN, {"status": "rejected"})
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header(
                "Access-Control-Allow-Headers", "Content-Type, X-Josie-Summit-Token"
            )
            self.send_header("Access-Control-Max-Age", "300")
            self.send_header("Vary", "Origin")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/health":
                with contact_lock:
                    contacts = dict(contact_stats)
                self._send(HTTPStatus.OK, {
                    "status": "ok", "relay_version": RELAY_VERSION,
                    "binding": "loopback_only", "bounded_exchange_rounds": 3,
                    "autonomous_routing": False, "production_actions": False,
                    "extension_contact": contacts,
                    "job": controller.status(),
                })
                return
            if self.path != "/next":
                self._send(HTTPStatus.NOT_FOUND, {"status": "not_found"}, cors=True)
                return
            authorized = self._authorized()
            with contact_lock:
                contact_stats["extension_contacts"] += 1
                contact_stats["authorized_contacts" if authorized else "rejected_contacts"] += 1
            if not authorized:
                self._send(HTTPStatus.FORBIDDEN, {"status": "rejected"}, cors=True)
                return
            action = controller.next_action()
            self._send(HTTPStatus.OK, {
                "status": "action" if action else "idle", "action": action,
                "job": controller.status(),
            }, cors=True)

        def do_POST(self) -> None:
            if self.path != "/result":
                self._send(HTTPStatus.NOT_FOUND, {"status": "not_found"}, cors=True)
                return
            if not self._authorized():
                self._send(HTTPStatus.FORBIDDEN, {"status": "rejected"}, cors=True)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if not 1 <= length <= 25_000:
                self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "rejected"}, cors=True)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = controller.submit_result(payload)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {
                    "status": "rejected", "reason": str(exc)[:200],
                }, cors=True)
                return
            self._send(HTTPStatus.OK, {"status": "accepted", "job": result}, cors=True)

    return SummitRelayHandler


def run_relay(*, project_root: Path, acceptance: bool) -> None:
    config = load_relay_config(project_root)
    token = load_relay_token(project_root)
    receipts = ReceiptLog(project_root / "data" / "summit-relay" / "receipts.jsonl")
    controller = RelayController(config, receipts, acceptance=acceptance)
    handler = make_relay_handler(controller=controller, token=token)
    server = ThreadingHTTPServer((config["binding"], config["port"]), handler)
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Josie Summit Relay v0.1")
    parser.add_argument("serve", nargs="?", choices=["serve"], default="serve")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--acceptance", action="store_true",
        help="Queue only the fixed harmless Sophie/Bernie/Sophie/Josie acceptance exchange.",
    )
    args = parser.parse_args(argv)
    run_relay(project_root=args.project_root.resolve(), acceptance=args.acceptance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


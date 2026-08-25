"""Loopback-only intake for prayers deliberately selected by Dustin.

The bridge has no browser automation, page-scanning, reply, or cloud path.  It
accepts a small authenticated payload from the local Chrome extension, verifies
that the active page is one of the locally configured sources, and records only
the text Dustin selected.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from josie.storage import LocalStore


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8788
MAX_REQUEST_BYTES = 12_000
SOURCE_CONTEXTS = {
    "slack_prayer_team",
    "google_messages_giant_killers",
    "whatsapp_sunday",
}
ALLOWED_CAPTURE_KEYS = {"url", "title", "header", "selected_text", "received_at"}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean_text(value: object, *, label: str, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    clean = value.replace("\x00", "").strip()
    if not allow_empty and not clean:
        raise ValueError(f"{label} is required")
    if len(clean) > maximum:
        raise ValueError(f"{label} exceeds the {maximum}-character limit")
    return clean


def _canonical_locator(url: str, header: str) -> tuple[str, str]:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError("Prayer capture requires an HTTPS source page")

    path = parsed.path.rstrip("/") or "/"
    if hostname == "app.slack.com":
        parts = [part for part in path.split("/") if part]
        if len(parts) < 3 or parts[0] != "client":
            raise ValueError("The active Slack page is not a channel")
        locator = f"https://{hostname}/client/{parts[1]}/{parts[2]}"
    elif hostname == "messages.google.com":
        parts = [part for part in path.split("/") if part]
        if len(parts) < 5 or parts[:4] != ["web", "u", "0", "conversations"]:
            raise ValueError("The active Google Messages page is not a conversation")
        locator = f"https://{hostname}/web/u/0/conversations/{parts[4]}"
    elif hostname == "web.whatsapp.com":
        clean_header = _clean_text(
            header, label="WhatsApp conversation heading", maximum=160
        )
        locator = f"https://{hostname}/|{clean_header}"
    else:
        raise ValueError("The active site is not an approved prayer source")
    return hostname, locator


def load_prayer_source_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "data" / "private" / "prayer-sources.json"
    if not path.is_file():
        raise ValueError("Local prayer source configuration is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Local prayer source configuration is invalid") from exc
    if not isinstance(data, dict) or set(data) != {"schema_version", "sources", "controls"}:
        raise ValueError("Local prayer source configuration has unexpected fields")
    if data["schema_version"] != 1 or not isinstance(data["sources"], list):
        raise ValueError("Local prayer source configuration has an invalid schema")
    if not isinstance(data["controls"], dict):
        raise ValueError("Local prayer source controls are invalid")
    required_controls = {
        "active_selection_only": True,
        "read_only": True,
        "cloud_processing": False,
        "sending": False,
        "cross_posting": False,
    }
    if any(data["controls"].get(key) is not value for key, value in required_controls.items()):
        raise ValueError("Local prayer source controls are not fail-closed")

    seen: set[str] = set()
    for source in data["sources"]:
        if not isinstance(source, dict) or set(source) != {
            "source_context", "hostname", "locator_sha256", "verified_at", "enabled"
        }:
            raise ValueError("A local prayer source has unexpected fields")
        context = source["source_context"]
        if context not in SOURCE_CONTEXTS or context in seen:
            raise ValueError("A local prayer source context is invalid or duplicated")
        seen.add(context)
        if source["hostname"] not in {
            "app.slack.com", "messages.google.com", "web.whatsapp.com"
        }:
            raise ValueError("A local prayer source hostname is invalid")
        digest = source["locator_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError("A local prayer source locator digest is invalid")
        if source["enabled"] is not True:
            raise ValueError("Disabled sources must be removed from the active configuration")
        _clean_text(source["verified_at"], label="Source verification time", maximum=50)
    if seen != SOURCE_CONTEXTS:
        raise ValueError("All three approved prayer sources must be configured")
    return data


def prayer_source_status(project_root: Path) -> dict[str, bool]:
    empty = {context: False for context in sorted(SOURCE_CONTEXTS)}
    try:
        config = load_prayer_source_config(project_root)
    except ValueError:
        return empty
    marker_path = project_root / "data" / "private" / "prayer-extension-installed.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(marker, dict) or marker.get("installed") is not True:
        return empty
    return {
        context: any(
            source["source_context"] == context and source["enabled"] is True
            for source in config["sources"]
        )
        for context in sorted(SOURCE_CONTEXTS)
    }


def prayer_bridge_status(project_root: Path) -> dict[str, object]:
    try:
        load_prayer_source_config(project_root)
        source_configuration_ready = True
    except ValueError:
        source_configuration_ready = False
    try:
        load_prayer_bridge_token(project_root)
        credential_ready = True
    except ValueError:
        credential_ready = False
    connections = prayer_source_status(project_root)
    extension_installed = all(connections.values())
    return {
        "status": "ready" if extension_installed else "extension_install_required",
        "source_configuration_ready": source_configuration_ready,
        "credential_ready": credential_ready,
        "capture_extension_installed": extension_installed,
        "source_connections": connections,
        "binding": "127.0.0.1:8788",
        "active_selection_only": True,
        "browser_scanning_enabled": False,
        "cloud_processing_enabled": False,
        "sending_enabled": False,
    }


def load_prayer_bridge_token(project_root: Path) -> str:
    path = project_root / "data" / "private" / "prayer-bridge.token"
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError("Local prayer bridge credential is missing") from exc
    if len(token) < 32 or len(token) > 200:
        raise ValueError("Local prayer bridge credential is invalid")
    return token


def ingest_prayer_capture(
    *, project_root: Path, store: LocalStore, payload: object
) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != ALLOWED_CAPTURE_KEYS:
        raise ValueError("Prayer capture payload has unexpected fields")
    selected_text = _clean_text(
        payload["selected_text"], label="Selected prayer text", maximum=4_000
    )
    url = _clean_text(payload["url"], label="Source URL", maximum=2_000)
    _clean_text(payload["title"], label="Page title", maximum=300, allow_empty=True)
    header = _clean_text(
        payload["header"], label="Conversation heading", maximum=160, allow_empty=True
    )
    received_at = _clean_text(
        payload["received_at"], label="Capture time", maximum=50
    )
    try:
        parsed_time = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Capture time is invalid") from exc
    if parsed_time.tzinfo is None:
        raise ValueError("Capture time must include a timezone")

    hostname, locator = _canonical_locator(url, header)
    locator_digest = _sha256(locator)
    config = load_prayer_source_config(project_root)
    matches = [
        source for source in config["sources"]
        if source["hostname"] == hostname
        and hmac.compare_digest(source["locator_sha256"], locator_digest)
    ]
    if len(matches) != 1:
        raise ValueError("The active conversation is not the locally approved source")
    source_context = str(matches[0]["source_context"])
    record = store.record_prayer_request(
        source_context=source_context,
        request_text=selected_text,
        received_at=received_at,
        requester_display="",
        identity_handling="omitted",
        source_reference=f"local-source:{_sha256(source_context + '|' + locator)[:24]}",
        sharing_scope="source_group_only",
        consent_notes="User-selected local capture; no redistribution permission inferred.",
        sensitivity="sensitive",
        provenance_status="direct_copy_unverified",
        confidence="medium",
    )
    return {
        "status": "recorded_local_only",
        "prayer_id": record["prayer_id"],
        "source_context": source_context,
        "duplicate_suggestion_ids": [
            int(item["prayer_id"]) for item in record["duplicate_suggestions"]
        ],
        "request_text_returned": False,
        "requester_identity_stored": False,
        "cloud_processing_authorized": False,
        "messages_sent": 0,
        "actions_executed": 0,
    }


def _valid_extension_origin(origin: str | None) -> bool:
    return bool(origin and origin.startswith("chrome-extension://") and len(origin) <= 100)


def make_prayer_bridge_handler(
    *, project_root: Path, store: LocalStore, token: str
) -> type[BaseHTTPRequestHandler]:
    class PrayerBridgeHandler(BaseHTTPRequestHandler):
        server_version = "JosiePrayerBridge/1.0"

        def log_message(self, format: str, *args: object) -> None:
            # Prayer paths, payloads, and browser details are intentionally omitted.
            return

        def _send(self, status: HTTPStatus, body: dict[str, object], *, cors: bool = False) -> None:
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
            supplied = self.headers.get("X-Josie-Prayer-Token", "")
            return hmac.compare_digest(supplied, token)

        def do_OPTIONS(self) -> None:
            origin = self.headers.get("Origin")
            if self.path != "/intake" or not _valid_extension_origin(origin):
                self._send(HTTPStatus.FORBIDDEN, {"status": "rejected"})
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header(
                "Access-Control-Allow-Headers", "Content-Type, X-Josie-Prayer-Token"
            )
            self.send_header("Access-Control-Max-Age", "300")
            self.send_header("Vary", "Origin")
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(HTTPStatus.OK, {
                    "status": "ok",
                    "binding": "loopback_only",
                    "active_selection_only": True,
                    "sending_enabled": False,
                    "cloud_processing_enabled": False,
                })
                return
            self._send(HTTPStatus.NOT_FOUND, {"status": "not_found"})

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            if self.path != "/intake":
                self._send(HTTPStatus.NOT_FOUND, {"status": "not_found"}, cors=True)
                return
            if not _valid_extension_origin(origin) or not self._authorized():
                self._send(HTTPStatus.FORBIDDEN, {"status": "rejected"}, cors=True)
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if not 1 <= content_length <= MAX_REQUEST_BYTES:
                self._send(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"status": "rejected", "reason": "invalid_request_size"},
                    cors=True,
                )
                return
            try:
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                result = ingest_prayer_capture(
                    project_root=project_root, store=store, payload=payload
                )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "rejected", "reason": "invalid_or_unapproved_capture"},
                    cors=True,
                )
                return
            self._send(HTTPStatus.CREATED, result, cors=True)

    return PrayerBridgeHandler


def run_prayer_bridge(
    *, project_root: Path, host: str = BRIDGE_HOST, port: int = BRIDGE_PORT
) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Prayer bridge may bind only to loopback")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Prayer bridge port is invalid")
    config = load_prayer_source_config(project_root)
    if len(config["sources"]) != 3:
        raise ValueError("Prayer bridge requires exactly three configured sources")
    token = load_prayer_bridge_token(project_root)
    store = LocalStore(project_root / "data" / "josie.db")
    handler = make_prayer_bridge_handler(
        project_root=project_root, store=store, token=token
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()

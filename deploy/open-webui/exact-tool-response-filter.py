"""Fail-closed Open WebUI outlet filter for authenticated Josie tool messages."""

from __future__ import annotations

import json
import os
import re
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


MODEL_ID = "josie-local:1.0"
CONNECTION_ID = "josie-core-review"
SOURCE_PREFIX = f"server:{CONNECTION_ID}/"
STATUS_SOURCE = f"{SOURCE_PREFIX}get_josie_status"
PROPOSAL_SOURCE = f"{SOURCE_PREFIX}record_review_proposal"
STATUS_URL = "http://proposal-server:3030/v1/status"
STATUS_KEYS = {
    "status",
    "read_only",
    "actions_queued",
    "actions_executed",
    "cloud_activity",
    "assistant_message",
}
PROPOSAL_KEYS = {
    "status",
    "proposal_id",
    "kind",
    "actions_queued",
    "actions_executed",
    "duplicate",
    "assistant_message",
}
ALLOWED_STATUS = {"ok", "warning", "critical", "stale"}
ALLOWED_KINDS = {"health_check", "memory_export", "restore_drill"}
STATUS_QUERY = re.compile(
    r"\b(current system status|your current status|your system status|"
    r"josie status|system health|current health|health check|"
    r"how much (?:disk |storage )?space|space (?:is )?left on [cd](?: drive)?)\b",
    re.IGNORECASE,
)


def _message(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 1_024:
        raise ValueError("assistant_message is invalid")
    if not value.endswith("Actions queued: 0. Actions executed: 0."):
        raise ValueError("assistant_message does not prove zero execution")
    return value


def _status_message(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != STATUS_KEYS:
        raise ValueError("status response schema is invalid")
    if (
        payload.get("status") not in ALLOWED_STATUS
        or payload.get("read_only") is not True
        or payload.get("actions_queued") != 0
        or payload.get("actions_executed") != 0
        or payload.get("cloud_activity") is not False
    ):
        raise ValueError("status response safety fields are invalid")
    message = _message(payload.get("assistant_message"))
    if not message.startswith("Read-only Josie status:"):
        raise ValueError("status message prefix is invalid")
    return message


def _proposal_message(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != PROPOSAL_KEYS:
        raise ValueError("proposal response schema is invalid")
    if (
        payload.get("status") != "review_required"
        or payload.get("kind") not in ALLOWED_KINDS
        or not isinstance(payload.get("proposal_id"), str)
        or not payload.get("proposal_id")
        or payload.get("actions_queued") != 0
        or payload.get("actions_executed") != 0
        or not isinstance(payload.get("duplicate"), bool)
    ):
        raise ValueError("proposal response safety fields are invalid")
    message = _message(payload.get("assistant_message"))
    if not message.startswith("No action was performed."):
        raise ValueError("proposal message prefix is invalid")
    return message


def _trusted_source_message(body: dict) -> str | None:
    candidates = []
    candidates.extend(body.get("sources") or [])
    candidates.extend((body.get("metadata") or {}).get("sources") or [])
    for message in body.get("messages") or []:
        if isinstance(message, dict):
            candidates.extend(message.get("sources") or [])

    for source in candidates:
        if not isinstance(source, dict) or source.get("tool_result") is not True:
            continue
        source_name = (source.get("source") or {}).get("name")
        if source_name not in {STATUS_SOURCE, PROPOSAL_SOURCE}:
            continue
        documents = source.get("document") or []
        if not isinstance(documents, list):
            continue
        for document in documents:
            if not isinstance(document, str) or len(document) > 4_096:
                continue
            try:
                payload = json.loads(document)
                return (
                    _status_message(payload)
                    if source_name == STATUS_SOURCE
                    else _proposal_message(payload)
                )
            except (ValueError, json.JSONDecodeError):
                continue
    return None


def _last_user_text(body: dict) -> str:
    for message in reversed(body.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def _status_token() -> str:
    connections = json.loads(os.environ.get("TOOL_SERVER_CONNECTIONS", "[]"))
    connection = next(
        (
            item
            for item in connections
            if (item.get("info") or {}).get("id") == CONNECTION_ID
        ),
        None,
    )
    if not isinstance(connection, dict) or not isinstance(connection.get("key"), str):
        raise ValueError("private status credential is unavailable")
    return connection["key"]


def _fresh_status_message() -> str:
    request = Request(
        STATUS_URL,
        headers={"Authorization": f"Bearer {_status_token()}"},
    )
    with urlopen(request, timeout=5) as response:
        if response.status != 200:
            raise ValueError("private status service rejected the request")
        raw = response.read(4_097)
    if len(raw) > 4_096:
        raise ValueError("status response exceeds size limit")
    return _status_message(json.loads(raw))


def _replace_last_assistant(body: dict, content: str) -> dict:
    messages = list(body.get("messages") or [])
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "assistant":
            messages[index] = {**message, "content": content}
            return {**body, "messages": messages}
    raise ValueError("assistant response is unavailable")


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=-100)

    def __init__(self):
        self.valves = self.Valves()

    def outlet(self, body: dict, __model__: dict | None = None) -> dict:
        model_id = body.get("model") or ((__model__ or {}).get("id"))
        if model_id != MODEL_ID:
            return body

        trusted = _trusted_source_message(body)
        if trusted is None and STATUS_QUERY.search(_last_user_text(body)):
            trusted = _fresh_status_message()
        return _replace_last_assistant(body, trusted) if trusted is not None else body

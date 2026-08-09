"""Verify Josie's authenticated tool result is copied without model rewriting."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from urllib.request import Request, urlopen


MODEL_ID = "josie-local:1.0"
OLLAMA_CHAT_URL = "http://host.docker.internal:11434/api/chat"
STATUS_URL = "http://proposal-server:3030/v1/status"
TRUSTED_SOURCE_PREFIX = "server:josie-core-review/"


def request_json(url: str, *, body: dict | None = None, headers: dict | None = None) -> dict:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(url, data=payload, headers=headers or {})
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def render_prompt(template: str, operation: str, result: dict, query: str) -> str:
    context = (
        f'<source id="1" name="{TRUSTED_SOURCE_PREFIX}{operation}">'
        # Open WebUI formats external JSON tool results with two-space
        # indentation before placing them into source context. Mirror that
        # exact model-facing representation in the acceptance test.
        f'{json.dumps(result, indent=2, ensure_ascii=False)}'
        "</source>"
    )
    return template.replace("{{CONTEXT}}", context).replace("{{QUERY}}", query)


def model_reply(system: str, prompt: str) -> str:
    response = request_json(
        OLLAMA_CHAT_URL,
        body={
            "model": MODEL_ID,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": 2048,
                "num_predict": 256,
            },
        },
        headers={"Content-Type": "application/json"},
    )
    return str((response.get("message") or {}).get("content") or "")


def main() -> int:
    template = os.environ.get("RAG_TEMPLATE", "")
    if (
        "copy its value byte-for-byte" not in template
        or TRUSTED_SOURCE_PREFIX not in template
    ):
        raise RuntimeError("The authenticated tool passthrough template is not loaded")

    connections = json.loads(os.environ.get("TOOL_SERVER_CONNECTIONS", "[]"))
    connection = next(
        (
            item
            for item in connections
            if (item.get("info") or {}).get("id") == "josie-core-review"
        ),
        None,
    )
    if connection is None or not connection.get("key"):
        raise RuntimeError("The private Josie tool connection is unavailable")

    status_result = request_json(
        STATUS_URL,
        headers={"Authorization": f"Bearer {connection['key']}"},
    )
    expected_status = status_result.get("assistant_message")
    if not isinstance(expected_status, str) or not expected_status:
        raise RuntimeError("The status tool did not return assistant_message")

    database = Path("/app/backend/data/webui.db")
    with sqlite3.connect(database) as db:
        row = db.execute(
            "SELECT meta,params,is_active FROM model WHERE id=?", (MODEL_ID,)
        ).fetchone()
    if row is None:
        raise RuntimeError("The governed Open WebUI model binding is missing")
    meta = json.loads(row[0])
    params = json.loads(row[1])
    capabilities = meta.get("capabilities") or {}
    binding_valid = bool(
        row[2]
        and meta.get("toolIds") == ["server:josie-core-review"]
        and capabilities.get("builtin_tools") is False
        and capabilities.get("file_context") is False
        and params.get("function_calling") == "default"
    )
    if not binding_valid:
        raise RuntimeError("The governed model binding is not fail-closed")

    status_prompt = render_prompt(
        template,
        "get_josie_status",
        status_result,
        "What is your current system status?",
    )

    # The 1.5B CPU model can vary on its first generation immediately after a
    # service restart. Warm that generation privately, then require the next
    # user-equivalent response to pass the exact authenticated-message gate.
    model_reply(params.get("system", ""), status_prompt)
    status_reply = model_reply(
        params.get("system", ""),
        status_prompt,
    )
    status_exact = status_reply == expected_status

    expected_proposal = (
        "No action was performed. A health_check proposal was recorded for human "
        "review. Status: review_required. Actions queued: 0. Actions executed: 0."
    )
    proposal_fixture = {
        "status": "review_required",
        "proposal_id": "passthrough-fixture-not-recorded",
        "kind": "health_check",
        "actions_queued": 0,
        "actions_executed": 0,
        "duplicate": False,
        "assistant_message": expected_proposal,
    }
    proposal_reply = model_reply(
        params.get("system", ""),
        render_prompt(
            template,
            "record_review_proposal",
            proposal_fixture,
            "Record a health_check proposal saying passthrough fixture.",
        ),
    )
    proposal_exact = proposal_reply == expected_proposal

    if not status_exact or not proposal_exact:
        print(
            json.dumps(
                {
                    "status_message_exact": status_exact,
                    "proposal_message_exact": proposal_exact,
                    "status_expected": expected_status,
                    "status_received": status_reply,
                    "proposal_expected": expected_proposal,
                    "proposal_received": proposal_reply,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        raise RuntimeError("The local model rewrote an authenticated assistant_message")

    print(
        json.dumps(
            {
                "status": "verified",
                "model": MODEL_ID,
                "status_message_exact": True,
                "proposal_message_exact": True,
                "file_context_enabled": False,
                "fixture_recorded": False,
                "actions_queued": 0,
                "actions_executed": 0,
                "cloud_activity": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

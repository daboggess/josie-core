"""Run one reversible Maintainer Mode job through the real Open WebUI path."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4


MODEL_ID = "josie-local:1.0"
FILTER_ID = "josie_exact_tool_response"
BASE_URL = "http://127.0.0.1:8080"
SOURCE_NAME = "server:josie-subscription-seats/maintain_josie_text"
TARGET = "docs/operations/MAINTAINER_ACCEPTANCE.md"
PROMPT = (
    'Maintainer Mode: in docs/operations/MAINTAINER_ACCEPTANCE.md replace '
    '"Maintainer acceptance status: pending." with '
    '"Maintainer acceptance status: verified through Open WebUI.".'
)


def request_json(url: str, token: str, body: dict) -> dict:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=360) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("Open WebUI returned a non-object response")
    return payload


def completion_content(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Open WebUI completion failed: {payload}")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("Open WebUI completion returned no assistant text")
    return message["content"]


def finalize(
    token: str,
    *,
    scope_id: str,
    user_message_id: str,
    assistant_message_id: str,
    raw_content: str,
) -> tuple[str, list[dict]]:
    payload = request_json(
        BASE_URL + "/api/chat/completed",
        token,
        {
            "model": MODEL_ID,
            "chat_id": scope_id,
            "id": assistant_message_id,
            "parent_id": user_message_id,
            "session_id": f"maintainer-acceptance-{scope_id}",
            "filter_ids": [FILTER_ID],
            "messages": [
                {"id": user_message_id, "role": "user", "content": PROMPT},
                {
                    "id": assistant_message_id,
                    "parentId": user_message_id,
                    "role": "assistant",
                    "content": raw_content,
                    "model": MODEL_ID,
                },
            ],
        },
    )
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("Open WebUI finalization returned no messages")
    assistant = messages[-1]
    if not isinstance(assistant, dict) or not isinstance(assistant.get("content"), str):
        raise RuntimeError("Open WebUI outlet returned no assistant text")
    sources = assistant.get("sources") or payload.get("sources") or []
    if not isinstance(sources, list):
        raise RuntimeError("Open WebUI outlet returned invalid sources")
    return assistant["content"], [item for item in sources if isinstance(item, dict)]


def maintenance_evidence(sources: list[dict]) -> dict:
    matches = [
        source
        for source in sources
        if (source.get("source") or {}).get("name") == SOURCE_NAME
    ]
    if len(matches) != 1:
        raise RuntimeError("Open WebUI did not return one Maintainer evidence source")
    documents = matches[0].get("document") or []
    if len(documents) != 1 or not isinstance(documents[0], str):
        raise RuntimeError("Maintainer evidence document is invalid")
    payload = json.loads(documents[0])
    if not isinstance(payload, dict):
        raise RuntimeError("Maintainer evidence payload is invalid")
    return payload


def save_chat(token: str, content: str, sources: list[dict]) -> str:
    now = int(time.time())
    user_id = str(uuid4())
    assistant_id = str(uuid4())
    user_message = {
        "id": user_id,
        "parentId": None,
        "childrenIds": [assistant_id],
        "role": "user",
        "content": PROMPT,
        "timestamp": now,
    }
    assistant_message = {
        "id": assistant_id,
        "parentId": user_id,
        "childrenIds": [],
        "role": "assistant",
        "content": content,
        "model": MODEL_ID,
        "modelName": "Josie",
        "sources": sources,
        "timestamp": now,
        "done": True,
    }
    chat = {
        "id": "",
        "title": "Josie Maintainer Mode 0.1 Acceptance",
        "models": [MODEL_ID],
        "params": {},
        "history": {
            "messages": {user_id: user_message, assistant_id: assistant_message},
            "currentId": assistant_id,
        },
        "messages": [user_message, assistant_message],
        "tags": [],
        "timestamp": now,
        "files": [],
    }
    saved = request_json(BASE_URL + "/api/v1/chats/new", token, {"chat": chat})
    chat_id = saved.get("id")
    if not isinstance(chat_id, str) or not chat_id:
        raise RuntimeError("Open WebUI did not persist the acceptance chat")
    return chat_id


def main() -> int:
    sys.path.insert(0, "/app/backend")
    if not os.environ.get("WEBUI_SECRET_KEY"):
        secret_path = Path("/app/backend/.webui_secret_key")
        os.environ["WEBUI_SECRET_KEY"] = secret_path.read_text(
            encoding="utf-8"
        ).strip()
    import asyncio
    from open_webui.models.users import Users
    from open_webui.utils.auth import create_token

    owner = asyncio.run(Users.get_super_admin_user())
    if owner is None:
        raise RuntimeError("Open WebUI has no administrator account")
    token = create_token({"id": owner.id}, expires_delta=timedelta(minutes=15))
    scope_id = str(uuid4())
    user_message_id = str(uuid4())
    assistant_message_id = str(uuid4())
    completion = request_json(
        BASE_URL + "/api/chat/completions",
        token,
        {
            "model": MODEL_ID,
            "chat_id": scope_id,
            "id": assistant_message_id,
            "parent_id": user_message_id,
            "messages": [{"role": "user", "content": PROMPT}],
            "stream": False,
            "tool_ids": [
                "server:josie-core-review",
                "server:josie-subscription-seats",
            ],
            "filter_ids": [FILTER_ID],
        },
    )
    raw_content = completion_content(completion)
    content, sources = finalize(
        token,
        scope_id=scope_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        raw_content=raw_content,
    )
    evidence = maintenance_evidence(sources)
    checks = {
        "status_completed": evidence.get("status") == "completed",
        "one_intended_file": evidence.get("files_changed") == [TARGET],
        "tests_passed": (evidence.get("tests") or {}).get("status") == "passed",
        "commit_recorded": isinstance(evidence.get("final_commit"), str)
        and len(evidence["final_commit"]) == 40,
        "checkpoint_recorded": isinstance(evidence.get("base_commit"), str)
        and len(evidence["base_commit"]) == 40,
        "branch_recorded": str(evidence.get("maintenance_branch") or "").startswith(
            "maintenance/"
        ),
        "diff_recorded": bool(evidence.get("diff_summary")),
        "commands_recorded": bool(evidence.get("commands")),
        "events_recorded": bool(evidence.get("events")),
        "rollback_recorded": "git revert" in str(evidence.get("rollback_result") or ""),
        "approval_not_required": evidence.get("approval_required") is False,
        "no_push": evidence.get("push_performed") is False,
        "no_arbitrary_shell": evidence.get("arbitrary_shell_available") is False,
        "authoritative_display": content == evidence.get("assistant_message"),
        "fabricated_local_text_replaced": raw_content != content,
    }
    if not all(checks.values()):
        raise RuntimeError(
            f"Maintainer acceptance failed: {checks}; content={content}; evidence={evidence}"
        )
    chat_id = save_chat(token, content, sources)
    print(
        json.dumps(
            {
                "status": "passed",
                "request_id": evidence["request_id"],
                "maintenance_branch": evidence["maintenance_branch"],
                "base_commit": evidence["base_commit"],
                "commit": evidence["final_commit"],
                "openwebui_chat_id": chat_id,
                "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
                "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "checks": checks,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

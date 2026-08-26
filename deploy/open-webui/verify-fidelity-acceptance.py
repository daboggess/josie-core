"""Repeat the exact failed Josie acceptance prompt through Open WebUI's local API."""

from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4


MODEL_ID = "josie-local:1.0"
FAILED_CHAT_ID = "33b44e6d-37bf-476b-9fcc-8128d9868585"
FAILED_USER_MESSAGE_ID = "55fbeac7-9bd9-410a-96cb-c2a513ca07c3"
DATABASE = Path("/app/backend/data/webui.db")
BASE_URL = "http://127.0.0.1:8080"


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
    with urlopen(request, timeout=240) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError("Open WebUI returned a non-object response")
    return payload


def failed_prompt() -> str:
    with sqlite3.connect(DATABASE) as database:
        row = database.execute(
            "SELECT chat FROM chat WHERE id=?", (FAILED_CHAT_ID,)
        ).fetchone()
    if row is None:
        raise RuntimeError("The original failed acceptance chat is unavailable")
    chat = json.loads(row[0])
    message = (chat.get("history") or {}).get("messages", {}).get(
        FAILED_USER_MESSAGE_ID
    )
    prompt = message.get("content") if isinstance(message, dict) else None
    if not isinstance(prompt, str) or not prompt:
        raise RuntimeError("The original acceptance prompt is unavailable")
    return prompt


def completion_content(payload: dict) -> tuple[str, list]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Open WebUI completion failed: {payload}")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("Open WebUI completion did not contain assistant text")
    sources = message.get("sources") or payload.get("sources") or []
    return message["content"], sources if isinstance(sources, list) else []


def evidence_checks(content: str, sources: list) -> dict[str, bool]:
    results = {
        "codex_display_exact": False,
        "gemini_display_exact": False,
        "local_recall_source_exact": False,
        "state_display_exact": False,
        "state_false_facts": False,
    }
    for source in sources:
        if not isinstance(source, dict):
            continue
        name = (source.get("source") or {}).get("name", "")
        documents = source.get("document") or []
        if not documents or not isinstance(documents[0], str):
            continue
        payload = json.loads(documents[0])
        if name.endswith("consult_codex"):
            expected = (
                "CODEX — ACTUAL CONSULTANT RESULT\n\n" + payload["response"]
                if payload["status"] == "ok"
                else str(payload["error"])
            )
            results["codex_display_exact"] = expected in content
        elif name.endswith("consult_gemini"):
            expected = (
                "GEMINI — ACTUAL CONSULTANT RESULT\n\n" + payload["response"]
                if payload["status"] == "ok"
                else str(payload["error"])
            )
            results["gemini_display_exact"] = expected in content
        elif name.endswith("recall_josie_history"):
            results["local_recall_source_exact"] = bool(
                payload.get("source") == "local_sqlite"
                and payload.get("query")
                == "What did we decide about Summit, Groq, and why we stopped "
                "pursuing that architecture as the primary direction?"
            )
        elif name.endswith("get_josie_conversation_state"):
            results["state_display_exact"] = payload.get("assistant_message") in content
            results["state_false_facts"] = all(
                payload.get(field) is False
                for field in (
                    "summit_groq_active",
                    "complete_chatgpt_history_imported",
                    "complete_gemini_history_imported",
                    "unified_history_importer_built",
                )
            )
    return results


def save_chat(token: str, prompt: str, content: str, sources: list) -> str:
    now = int(time.time())
    user_id = str(uuid4())
    assistant_id = str(uuid4())
    user_message = {
        "id": user_id,
        "parentId": None,
        "childrenIds": [assistant_id],
        "role": "user",
        "content": prompt,
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
        "title": "Josie Tool Fidelity Acceptance",
        "models": [MODEL_ID],
        "params": {},
        "history": {
            "messages": {
                user_id: user_message,
                assistant_id: assistant_message,
            },
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


def finalize_completion(
    token: str,
    *,
    scope_id: str,
    user_message_id: str,
    assistant_message_id: str,
    prompt: str,
    raw_content: str,
) -> tuple[str, list]:
    finalized = request_json(
        BASE_URL + "/api/chat/completed",
        token,
        {
            "model": MODEL_ID,
            "chat_id": scope_id,
            "id": assistant_message_id,
            "parent_id": user_message_id,
            "session_id": f"acceptance-{scope_id}",
            "filter_ids": ["josie_exact_tool_response"],
            "messages": [
                {
                    "id": user_message_id,
                    "role": "user",
                    "content": prompt,
                },
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
    messages = finalized.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("Open WebUI completion finalization returned no messages")
    assistant = messages[-1]
    if not isinstance(assistant, dict) or not isinstance(assistant.get("content"), str):
        raise RuntimeError("Open WebUI outlet filter returned no assistant text")
    sources = assistant.get("sources") or finalized.get("sources") or []
    return assistant["content"], sources if isinstance(sources, list) else []


def main() -> int:
    sys.path.insert(0, "/app/backend")
    if not os.environ.get("WEBUI_SECRET_KEY"):
        secret_path = Path("/app/backend/.webui_secret_key")
        os.environ["WEBUI_SECRET_KEY"] = secret_path.read_text(
            encoding="utf-8"
        ).strip()
    from open_webui.models.users import Users
    from open_webui.utils.auth import create_token

    owner = Users.get_super_admin_user()
    if owner is None:
        raise RuntimeError("Open WebUI has no administrator account")
    token = create_token({"id": owner.id}, expires_delta=timedelta(minutes=15))
    prompt = failed_prompt()
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
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "tool_ids": [
                "server:josie-core-review",
                "server:josie-subscription-seats",
            ],
            "filter_ids": ["josie_exact_tool_response"],
        },
    )
    raw_content, _ = completion_content(completion)
    content, sources = finalize_completion(
        token,
        scope_id=scope_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        prompt=prompt,
        raw_content=raw_content,
    )
    checks = {
        "codex_actual": "CODEX — ACTUAL CONSULTANT RESULT" in content,
        "gemini_real_outcome": (
            "GEMINI — ACTUAL CONSULTANT RESULT" in content
            or "GEMINI — CONSULTATION UNAVAILABLE" in content
        ),
        "summit_groq_inactive": "Summit/Groq route active: false." in content,
        "chatgpt_history_not_imported": (
            "Complete ChatGPT history imported: false." in content
        ),
        "gemini_history_not_imported": (
            "Complete Gemini history imported: false." in content
        ),
        "importer_not_built": "Unified History Importer built: false." in content,
        "tests_passed": "status=passed." in content,
        "local_memory_actual": "LOCAL MEMORY — ACTUAL SQLITE MATCHES" in content,
    }
    checks.update(evidence_checks(content, sources))
    if not all(checks.values()):
        raise RuntimeError(f"Fidelity acceptance failed: {checks}; response={content}")
    chat_id = save_chat(token, prompt, content, sources)
    print(
        json.dumps(
            {
                "status": "passed",
                "source_chat_id": FAILED_CHAT_ID,
                "acceptance_chat_id": chat_id,
                "prompt_sha256": __import__("hashlib").sha256(
                    prompt.encode("utf-8")
                ).hexdigest(),
                "response_sha256": __import__("hashlib").sha256(
                    content.encode("utf-8")
                ).hexdigest(),
                "response_chars": len(content),
                "source_count": len(sources),
                "completion_finalized_endpoint": True,
                "checks": checks,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify ordinary chat and explicit local delegation through Josie 8B."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4


MODEL_ID = "josie-qwen3-8b:1.0"
BASE_MODEL_ID = "josie-qual-qwen3:8b-32k"
FILTER_ID = "josie_exact_tool_response"
TOOL_IDS = ["server:josie-core-review", "server:josie-subscription-seats"]
BASE_URL = "http://127.0.0.1:8080"
ORDINARY_PROMPT = "Reply with one short friendly sentence. Do not use tools."
DELEGATE_PROMPT = (
    "Delegate Local: Run `python --version` in D:\\Josie. Do not change any files."
)


def post(url: str, token: str, body: dict, *, timeout: int) -> tuple[str, str]:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.headers.get_content_type(), response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Open WebUI HTTP {exc.code} from {url}: {detail}") from exc


def completion_text(content_type: str, raw: str) -> str:
    if content_type == "application/json":
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices") or []
        message = (choices[0].get("message") if choices else None) or {}
        return str(message.get("content") or "")
    chunks = []
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        try:
            payload = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices") or []
        if choices:
            chunks.append(str((choices[0].get("delta") or {}).get("content") or ""))
        elif isinstance(payload.get("content"), str):
            chunks.append(payload["content"])
    return "".join(chunks)


def completion(token: str, prompt: str) -> tuple[str, str, str]:
    scope_id = str(uuid4())
    user_id = str(uuid4())
    assistant_id = str(uuid4())
    content_type, raw = post(
        BASE_URL + "/api/chat/completions",
        token,
        {
            "model": MODEL_ID,
            "chat_id": scope_id,
            "id": assistant_id,
            "parent_id": user_id,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "tool_ids": TOOL_IDS,
            "filter_ids": [FILTER_ID],
        },
        timeout=120,
    )
    raw_content = completion_text(content_type, raw)
    _, finalized_raw = post(
        BASE_URL + "/api/chat/completed",
        token,
        {
            "model": MODEL_ID,
            "chat_id": scope_id,
            "id": assistant_id,
            "parent_id": user_id,
            "session_id": f"qwen3-frontdoor-{scope_id}",
            "filter_ids": [FILTER_ID],
            "messages": [
                {"id": user_id, "role": "user", "content": prompt},
                {
                    "id": assistant_id,
                    "parentId": user_id,
                    "role": "assistant",
                    "content": raw_content,
                    "model": MODEL_ID,
                },
            ],
        },
        timeout=1000,
    )
    finalized = json.loads(finalized_raw)
    messages = finalized.get("messages") or []
    if not messages or not isinstance(messages[-1].get("content"), str):
        raise RuntimeError(f"Open WebUI finalization returned no assistant text: {finalized}")
    return raw_content, messages[-1]["content"], scope_id


async def owner_token() -> str:
    sys.path.insert(0, "/app/backend")
    if not os.environ.get("WEBUI_SECRET_KEY"):
        os.environ["WEBUI_SECRET_KEY"] = Path(
            "/app/backend/.webui_secret_key"
        ).read_text(encoding="utf-8").strip()
    from open_webui.models.users import Users
    from open_webui.utils.auth import create_token

    owner = await Users.get_super_admin_user()
    if owner is None:
        raise RuntimeError("Open WebUI has no administrator account")
    return create_token({"id": owner.id}, expires_delta=timedelta(minutes=20))


def main() -> int:
    token = asyncio.run(owner_token())
    ordinary_raw, ordinary_final, ordinary_scope = completion(token, ORDINARY_PROMPT)
    if not ordinary_final.strip():
        raise RuntimeError("Josie 8B ordinary chat returned no content")
    if "JOSIE LOCAL CODE" in ordinary_final:
        raise RuntimeError("Ordinary chat unexpectedly invoked local execution")
    delegate_raw, delegate_final, delegate_scope = completion(token, DELEGATE_PROMPT)
    if not delegate_final.startswith("JOSIE LOCAL CODE — ACTUAL RESULT"):
        raise RuntimeError(f"Delegation did not return a validated receipt: {delegate_final}")
    required = (
        "Runtime/model: OpenCode / ollama/josie-qual-qwen3:8b-32k",
        "Status: completed",
        "Exit: 0 | Timeout: False",
        "Changed files: none verified",
        "Thermal safety: none",
    )
    missing = [item for item in required if item not in delegate_final]
    if missing:
        raise RuntimeError(f"Delegation receipt is missing {missing}: {delegate_final}")
    print(json.dumps({
        "model": MODEL_ID,
        "base_model": BASE_MODEL_ID,
        "ordinary_scope": ordinary_scope,
        "ordinary_raw": ordinary_raw,
        "ordinary_final": ordinary_final,
        "ordinary_execution_triggered": False,
        "delegate_scope": delegate_scope,
        "delegate_raw": delegate_raw,
        "delegate_final": delegate_final,
        "codex_used": False,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

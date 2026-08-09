"""Idempotently bind Josie's bounded tools to the local Open WebUI model."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, "/app/backend")
if not os.environ.get("WEBUI_SECRET_KEY"):
    secret_path = Path("/app/backend/.webui_secret_key")
    if not secret_path.is_file():
        raise RuntimeError("Open WebUI runtime secret file is unavailable")
    os.environ["WEBUI_SECRET_KEY"] = secret_path.read_text(encoding="utf-8").strip()
    if not os.environ["WEBUI_SECRET_KEY"]:
        raise RuntimeError("Open WebUI runtime secret file is empty")

from open_webui.models.models import ModelForm, Models
from open_webui.models.users import Users


MODEL_ID = "josie-local:1.0"
TOOL_ID = "server:josie-core-review"
SYSTEM_PROMPT = """You are Josie, a local-first assistant on Dustin's private machine.

For every request about current health, status, storage, disk space, services,
backups, proposals, or safety locks, you MUST call get_josie_status before
answering. Never claim current state from memory or guesswork. If the tool is
unavailable, say that current status could not be verified.

For requests to record a supported review proposal, call
record_review_proposal. A proposal is not an executed action. When either tool
returns assistant_message, reproduce assistant_message exactly and add no
claims. Never claim that an action, improvement, transaction, message, browser
operation, or cloud call occurred unless the tool result explicitly proves it.
"""


def main() -> int:
    owner = Users.get_super_admin_user()
    if owner is None:
        raise RuntimeError("Open WebUI has no administrator account")
    form = ModelForm(
        id=MODEL_ID,
        base_model_id=None,
        name="Josie 1.0",
        meta={
            "profile_image_url": "/static/favicon.png",
            "description": "Local Josie with a bounded read-only status and review bridge.",
            "capabilities": {"builtin_tools": False},
            "toolIds": [TOOL_ID],
        },
        params={
            # Qwen 2.5 1.5B can emit a plausible tool call as ordinary text
            # instead of Ollama's structured tool_calls field. Open WebUI's
            # default mode performs a separate, bounded JSON routing pass,
            # validates the selected name/parameters, and only then invokes
            # the private OpenAPI server.
            "function_calling": "default",
            "system": SYSTEM_PROMPT,
            "temperature": 0,
        },
        access_grants=[],
        is_active=True,
    )
    existing = Models.get_model_by_id(MODEL_ID)
    configured = (
        Models.update_model_by_id(MODEL_ID, form)
        if existing is not None
        else Models.insert_new_model(form, owner.id)
    )
    if configured is None:
        raise RuntimeError("Open WebUI model binding could not be saved")
    meta = configured.meta.model_dump()
    params = configured.params.model_dump()
    valid = bool(
        configured.base_model_id is None
        and configured.is_active
        and meta.get("toolIds") == [TOOL_ID]
        and (meta.get("capabilities") or {}).get("builtin_tools") is False
        and params.get("function_calling") == "default"
        and "MUST call get_josie_status" in str(params.get("system", ""))
    )
    if not valid:
        raise RuntimeError("Open WebUI model binding failed closed validation")
    print(
        json.dumps(
            {
                "status": "configured",
                "model": MODEL_ID,
                "default_tool_ids": [TOOL_ID],
                "function_calling": "default",
                "routing": "bounded_json_preflight",
                "builtin_tools_enabled": False,
                "cloud_activity": False,
                "actions_executed": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

from open_webui.models.functions import FunctionForm, Functions
from open_webui.models.models import ModelForm, Models
from open_webui.models.users import Users
from open_webui.utils.plugin import load_function_module_by_id


MODEL_ID = "josie-local:1.0"
TOOL_ID = "server:josie-core-review"
FILTER_ID = "josie_exact_tool_response"
FILTER_PATH = Path("/opt/josie/exact-tool-response-filter.py")
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
    filter_content = FILTER_PATH.read_text(encoding="utf-8")
    loaded_filter, loaded_filter_type, _ = load_function_module_by_id(
        FILTER_ID, filter_content
    )
    if loaded_filter_type != "filter" or not callable(getattr(loaded_filter, "outlet", None)):
        raise RuntimeError("Open WebUI cannot load the exact response filter")
    filter_form = FunctionForm(
        id=FILTER_ID,
        name="Josie Exact Tool Response",
        content=filter_content,
        meta={
            "description": "Copies only validated authenticated Josie tool messages."
        },
    )
    existing_filter = Functions.get_function_by_id(FILTER_ID)
    if existing_filter is None:
        configured_filter = Functions.insert_new_function(
            owner.id, "filter", filter_form
        )
    else:
        configured_filter = Functions.update_function_by_id(
            FILTER_ID,
            {
                **filter_form.model_dump(),
                "user_id": owner.id,
                "type": "filter",
                "is_active": True,
                "is_global": False,
            },
        )
    if configured_filter is None:
        raise RuntimeError("The exact authenticated response filter could not be saved")
    configured_filter = Functions.update_function_by_id(
        FILTER_ID, {"is_active": True, "is_global": False}
    )
    if configured_filter is None:
        raise RuntimeError("The exact authenticated response filter could not be activated")
    form = ModelForm(
        id=MODEL_ID,
        base_model_id=None,
        name="Josie 1.0",
        meta={
            "profile_image_url": "/static/favicon.png",
            "description": "Local Josie with a bounded read-only status and review bridge.",
            "capabilities": {"builtin_tools": False, "file_context": False},
            "toolIds": [TOOL_ID],
            "filterIds": [FILTER_ID],
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
        and meta.get("filterIds") == [FILTER_ID]
        and (meta.get("capabilities") or {}).get("builtin_tools") is False
        and (meta.get("capabilities") or {}).get("file_context") is False
        and params.get("function_calling") == "default"
        and "MUST call get_josie_status" in str(params.get("system", ""))
        and configured_filter.is_active
        and configured_filter.is_global is False
        and configured_filter.content == filter_content
    )
    if not valid:
        raise RuntimeError("Open WebUI model binding failed closed validation")
    print(
        json.dumps(
            {
                "status": "configured",
                "model": MODEL_ID,
                "default_tool_ids": [TOOL_ID],
                "response_filter_ids": [FILTER_ID],
                "response_filter_loader_verified": True,
                "function_calling": "default",
                "routing": "bounded_json_preflight",
                "builtin_tools_enabled": False,
                "file_context_enabled": False,
                "authenticated_message_passthrough": True,
                "authenticated_message_enforced_after_model": True,
                "cloud_activity": False,
                "actions_executed": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

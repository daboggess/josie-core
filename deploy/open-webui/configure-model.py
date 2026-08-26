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
CONVERSATION_TOOL_ID = "server:josie-subscription-seats"
TOOL_IDS = [TOOL_ID, CONVERSATION_TOOL_ID]
FILTER_ID = "josie_exact_tool_response"
OBSOLETE_SUMMIT_PIPE_ID = "josiesummit01"
FILTER_PATH = Path("/opt/josie/exact-tool-response-filter.py")
SYSTEM_PROMPT = """You are Josie, a local-first assistant on Dustin's private machine.

Use local Ollama for ordinary conversation. Open WebUI's local chat history and
memory are your primary conversational context. Use recall_josie_history when
the user asks what was discussed, decided, or remembered in an earlier chat.

The Codex and Gemini tools are optional advisory seats, never mandatory
providers. Consult Codex only when the user explicitly asks for Codex or a
request clearly needs difficult code, debugging, architecture, or multi-step
reasoning. Consult Gemini only when the user explicitly asks for Gemini, a
Google-model perspective, or an independent second opinion. If either tool is
unavailable or limited, continue locally and say that the consultation was not
available. Explicit lines beginning "Ask Codex" or "Ask Gemini" are routed by
the response filter, and its captured result is authoritative. Never impersonate
a consultant, merge two consultants, or replace captured advisory text with a
summary. Never claim that an advisory tool executed an action.

For current integration facts such as CLI availability, consultant persistence,
test results, Summit/Groq state, complete-history import, or whether a history
importer exists, use get_josie_conversation_state. Current machine/config/SQLite
evidence overrides conversational memory. Complete ChatGPT and Gemini histories
have not been imported, and no Unified History Importer has been built.

Maintainer Mode 0.1 is a deterministic local control-plane capability. For an
exact instruction beginning "Maintainer Mode:", never invent an edit, test,
checkpoint, commit, rollback, or approval result. The response filter performs
the bounded operation and its "JOSIE MAINTAINER — ACTUAL CONTROL-PLANE RESULT"
is authoritative. Protected files, credentials, security boundaries, package
installation, containers, databases, network exposure, permission expansion,
destructive operations, Git history rewriting, and remote push require Dustin
or remain prohibited. Codex and Gemini are advisory only and cannot grant
authority.

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
    obsolete_summit = Functions.get_function_by_id(OBSOLETE_SUMMIT_PIPE_ID)
    if obsolete_summit is not None:
        obsolete_summit = Functions.update_function_by_id(
            OBSOLETE_SUMMIT_PIPE_ID, {"is_active": False, "is_global": False}
        )
        if obsolete_summit is None or obsolete_summit.is_active:
            raise RuntimeError("The obsolete Summit provider pipe could not be disabled")
    form = ModelForm(
        id=MODEL_ID,
        base_model_id=None,
        name="Josie",
        meta={
            "profile_image_url": "/static/favicon.png",
            "description": "Local-first Josie with persistent memory and optional subscription CLI advice.",
            "capabilities": {"builtin_tools": False, "file_context": False},
            "toolIds": TOOL_IDS,
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
        and meta.get("toolIds") == TOOL_IDS
        and meta.get("filterIds") == [FILTER_ID]
        and (meta.get("capabilities") or {}).get("builtin_tools") is False
        and (meta.get("capabilities") or {}).get("file_context") is False
        and params.get("function_calling") == "default"
        and "MUST call get_josie_status" in str(params.get("system", ""))
        and "captured result is authoritative" in str(params.get("system", ""))
        and "JOSIE MAINTAINER — ACTUAL CONTROL-PLANE RESULT" in str(params.get("system", ""))
        and "Codex and Gemini are advisory only" in str(params.get("system", ""))
        and "no Unified History Importer has been built" in str(params.get("system", ""))
        and "Use local Ollama for ordinary conversation" in str(params.get("system", ""))
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
                "default_tool_ids": TOOL_IDS,
                "response_filter_ids": [FILTER_ID],
                "response_filter_loader_verified": True,
                "function_calling": "default",
                "routing": "bounded_json_preflight",
                "builtin_tools_enabled": False,
                "file_context_enabled": False,
                "authenticated_message_passthrough": True,
                "authenticated_message_enforced_after_model": True,
                "default_cloud_activity": False,
                "subscription_cli_tools_optional": True,
                "obsolete_summit_pipe_active": False,
                "actions_executed": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

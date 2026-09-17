"""Idempotently bind Josie's bounded tools to the local Open WebUI model."""

from __future__ import annotations

import asyncio
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
QWEN3_MODEL_ID = "josie-qwen3-8b:1.0"
QWEN3_BASE_MODEL_ID = "josie-qual-qwen3:8b-32k"
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


async def main() -> int:
    owner = await Users.get_super_admin_user()
    if owner is None:
        raise RuntimeError("Open WebUI has no administrator account")
    filter_content = FILTER_PATH.read_text(encoding="utf-8")
    loaded_filter, loaded_filter_type, _ = await load_function_module_by_id(
        FILTER_ID, filter_content
    )
    if (
        loaded_filter_type != "filter"
        or not callable(getattr(loaded_filter, "inlet", None))
        or not callable(getattr(loaded_filter, "outlet", None))
        or not callable(getattr(loaded_filter, "identity_bootstrap_status", None))
        or not callable(getattr(loaded_filter, "history_context_status", None))
    ):
        raise RuntimeError("Open WebUI cannot load the exact response filter")
    bootstrap_status = loaded_filter.identity_bootstrap_status()
    if bootstrap_status.get("status") not in {"available", "disabled"}:
        raise RuntimeError("Josie identity bootstrap validation failed")
    if bootstrap_status.get("status") == "available" and not (
        bootstrap_status.get("source_hashes_verified") is True
        and isinstance(bootstrap_status.get("version"), str)
        and int(bootstrap_status.get("source_count") or 0) >= 3
    ):
        raise RuntimeError("Josie identity bootstrap provenance validation failed")
    history_context_status = loaded_filter.history_context_status()
    if history_context_status.get("status") not in {"enabled", "disabled"}:
        raise RuntimeError("Josie history context configuration is invalid")
    if history_context_status.get("status") == "enabled" and not (
        history_context_status.get("schema_version") == 1
        and history_context_status.get("actions_executed") == 0
        and 2_000 <= int(history_context_status.get("max_packet_chars") or 0) <= 20_000
        and history_context_status.get("max_evidence") == 5
    ):
        raise RuntimeError("Josie history context safety validation failed")
    filter_form = FunctionForm(
        id=FILTER_ID,
        name="Josie Exact Tool Response",
        content=filter_content,
        meta={
            "description": "Copies only validated authenticated Josie tool messages."
        },
    )
    existing_filter = await Functions.get_function_by_id(FILTER_ID)
    if existing_filter is None:
        configured_filter = await Functions.insert_new_function(
            owner.id, "filter", filter_form
        )
    else:
        configured_filter = await Functions.update_function_by_id(
            FILTER_ID,
            {
                **filter_form.model_dump(),
                "user_id": owner.id,
                "type": "filter",
                "is_active": True,
                "is_global": True,
            },
        )
    if configured_filter is None:
        raise RuntimeError("The exact authenticated response filter could not be saved")
    configured_filter = await Functions.update_function_by_id(
        FILTER_ID, {"is_active": True, "is_global": True}
    )
    if configured_filter is None:
        raise RuntimeError("The exact authenticated response filter could not be activated")
    obsolete_summit = await Functions.get_function_by_id(OBSOLETE_SUMMIT_PIPE_ID)
    if obsolete_summit is not None:
        obsolete_summit = await Functions.update_function_by_id(
            OBSOLETE_SUMMIT_PIPE_ID, {"is_active": False, "is_global": False}
        )
        if obsolete_summit is None or obsolete_summit.is_active:
            raise RuntimeError("The obsolete Summit provider pipe could not be disabled")
    model_specs = (
        (MODEL_ID, None, "Josie"),
        ("josie-antigravity-flash", None, "Josie (Antigravity Flash)"),
        ("josie-antigravity-pro", None, "Josie (Antigravity Pro)"),
        ("qwen3:14b", None, "Josie (Local RTX 3060 - Qwen3 14B)"),
        ("gemma4:12b", None, "Josie (Local RTX 3060 - Gemma4 12B)"),
    )
    configured_models = []
    for model_id, base_model_id, display_name in model_specs:
        form = ModelForm(
            id=model_id,
            base_model_id=base_model_id,
            name=display_name,
            meta={
                "profile_image_url": "/static/favicon.png",
                "description": "Local-first Josie with persistent memory and optional subscription CLI advice.",
                "capabilities": {"builtin_tools": False, "file_context": False},
                "identity_bootstrap": bootstrap_status,
                "history_context": history_context_status,
                "toolIds": TOOL_IDS,
                "filterIds": [FILTER_ID],
            },
            params={
                # Default mode performs a separate, bounded JSON routing pass,
                # validates the selected name/parameters, and only then invokes
                # the private OpenAPI server.
                "function_calling": "default",
                "system": SYSTEM_PROMPT,
                "temperature": 0,
            },
            access_grants=[],
            is_active=True,
        )
        existing = await Models.get_model_by_id(model_id)
        configured = (
            await Models.update_model_by_id(model_id, form)
            if existing is not None
            else await Models.insert_new_model(form, owner.id)
        )
        if configured is None:
            raise RuntimeError(f"Open WebUI model binding could not be saved: {model_id}")
        meta = configured.meta.model_dump()
        params = configured.params.model_dump()
        valid = bool(
            configured.base_model_id == base_model_id
            and configured.is_active
            and meta.get("toolIds") == TOOL_IDS
            and meta.get("filterIds") == [FILTER_ID]
            and (meta.get("capabilities") or {}).get("builtin_tools") is False
            and (meta.get("capabilities") or {}).get("file_context") is False
            and (meta.get("identity_bootstrap") or {}).get("status")
            == bootstrap_status.get("status")
            and (meta.get("history_context") or {}).get("status")
            == history_context_status.get("status")
            and params.get("function_calling") == "default"
            and "MUST call get_josie_status" in str(params.get("system", ""))
            and "captured result is authoritative" in str(params.get("system", ""))
            and "JOSIE MAINTAINER — ACTUAL CONTROL-PLANE RESULT" in str(params.get("system", ""))
            and "Codex and Gemini are advisory only" in str(params.get("system", ""))
            and "no Unified History Importer has been built" in str(params.get("system", ""))
            and "Use local Ollama for ordinary conversation" in str(params.get("system", ""))
        )
        if not valid:
            raise RuntimeError(f"Open WebUI model binding failed closed validation: {model_id}")
        configured_models.append(configured)
    if not (configured_filter.is_active and configured_filter.is_global is True
            and configured_filter.content == filter_content):
        raise RuntimeError("Open WebUI response filter binding failed closed validation")

    # Ensure QWEN3_MODEL_ID is deactivated and hidden
    existing_qwen3 = await Models.get_model_by_id(QWEN3_MODEL_ID)
    if existing_qwen3 is not None:
        qwen3_form = ModelForm(
            id=existing_qwen3.id,
            name=existing_qwen3.name,
            base_model_id=existing_qwen3.base_model_id,
            meta=existing_qwen3.meta.model_dump() if hasattr(existing_qwen3.meta, "model_dump") else (existing_qwen3.meta or {}),
            params=existing_qwen3.params.model_dump() if hasattr(existing_qwen3.params, "model_dump") else (existing_qwen3.params or {}),
            access_grants=existing_qwen3.access_grants or [],
            is_active=False,
        )
        await Models.update_model_by_id(QWEN3_MODEL_ID, qwen3_form)

    # Hide all old, experimental, and benchmark Ollama models from the picker without deleting them
    models_to_hide = [
        "josie-bench-qwen3-14b-24k:latest",
        "josie-bench-qwen3-coder-16k:latest",
        "josie-bench-devstral-16k:latest",
        "josie-bench-qwen3-coder-32k:latest",
        "josie-bench-devstral-24k:latest",
        "qwen3-coder:30b-a3b-q4_K_M",
        "devstral-small-2:24b-instruct-2512-q4_K_M",
        "josie-qual-qwen3:8b-32k",
        "qwen3:8b",
        "josie-qual-qwen25-coder:7b-32k",
        "qwen2.5-coder:7b",
        "josie-code-local:1.5b-16k",
        "josie-local:pre-grounding",
        "qwen2.5:1.5b-instruct-q4_K_M",
        "arena-model",
    ]
    for hide_id in models_to_hide:
        existing = await Models.get_model_by_id(hide_id)
        if existing is not None:
            hide_form = ModelForm(
                id=existing.id,
                name=existing.name,
                base_model_id=None,
                meta=existing.meta.model_dump() if hasattr(existing.meta, "model_dump") else (existing.meta or {}),
                params=existing.params.model_dump() if hasattr(existing.params, "model_dump") else (existing.params or {}),
                access_grants=existing.access_grants or [],
                is_active=False,
            )
            await Models.update_model_by_id(hide_id, hide_form)
        else:
            hide_form = ModelForm(
                id=hide_id,
                name=hide_id,
                base_model_id=None,
                meta={},
                params={},
                access_grants=[],
                is_active=False,
            )
            await Models.insert_new_model(hide_form, owner.id)

    # Ensure worker models (qwen3:14b, gemma4:12b) are active without tools
    for worker_id in ("qwen3:14b", "gemma4:12b"):
        existing = await Models.get_model_by_id(worker_id)
        if existing is not None and not existing.is_active:
            worker_form = ModelForm(
                id=existing.id,
                name=existing.name,
                base_model_id=None,
                meta=existing.meta.model_dump() if hasattr(existing.meta, "model_dump") else (existing.meta or {}),
                params=existing.params.model_dump() if hasattr(existing.params, "model_dump") else (existing.params or {}),
                access_grants=existing.access_grants or [],
                is_active=True,
            )
            await Models.update_model_by_id(worker_id, worker_form)

    visible_models = [
        MODEL_ID,
        "qwen3:14b",
        "gemma4:12b",
        "josie-antigravity-flash",
        "josie-antigravity-pro",
    ]
    settings = dict(owner.settings or {})
    ui_settings = dict(settings.get("ui") or {})
    ui_settings["models"] = visible_models
    ui_settings["model"] = MODEL_ID
    settings["ui"] = ui_settings
    owner = await Users.update_user_settings_by_id(owner.id, settings)
    saved_settings = (
        owner.settings.model_dump() if owner is not None
        and hasattr(owner.settings, "model_dump") else (owner.settings if owner else {})
    )
    if (saved_settings or {}).get("ui", {}).get("models") != visible_models:
        raise RuntimeError("Open WebUI primary-model preference could not be saved")

    from open_webui.models.config import Config
    await Config.upsert({"ui.default_models": MODEL_ID})

    print(
        json.dumps(
            {
                "status": "configured",
                "models": visible_models,
                "primary_model": MODEL_ID,
                "default_tool_ids": TOOL_IDS,
                "response_filter_ids": [FILTER_ID],
                "response_filter_loader_verified": True,
                "function_calling": "default",
                "routing": "bounded_json_preflight",
                "builtin_tools_enabled": False,
                "file_context_enabled": False,
                "identity_bootstrap": bootstrap_status,
                "history_context": history_context_status,
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
    raise SystemExit(asyncio.run(main()))

"""Fail-closed Open WebUI outlet filter for authenticated Josie tool messages."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field


MODEL_ID = "josie-local:1.0"
CONNECTION_ID = "josie-core-review"
CONTROL_CONNECTION_ID = "josie-subscription-seats"
SOURCE_PREFIX = f"server:{CONNECTION_ID}/"
STATUS_SOURCE = f"{SOURCE_PREFIX}get_josie_status"
PROPOSAL_SOURCE = f"{SOURCE_PREFIX}record_review_proposal"
STATUS_URL = "http://proposal-server:3030/v1/status"
HISTORY_URL = "http://host.docker.internal:8790/v1/history"
CONTROL_URL = "http://host.docker.internal:8790"
CONTROL_SOURCE_PREFIX = f"server:{CONTROL_CONNECTION_ID}/"
CODEX_SOURCE = f"{CONTROL_SOURCE_PREFIX}consult_codex"
GEMINI_SOURCE = f"{CONTROL_SOURCE_PREFIX}consult_gemini"
STATE_SOURCE = f"{CONTROL_SOURCE_PREFIX}get_josie_conversation_state"
RECALL_SOURCE = f"{CONTROL_SOURCE_PREFIX}recall_josie_history"
MAINTAINER_SOURCE = f"{CONTROL_SOURCE_PREFIX}maintain_josie_text"
MAINTAINER_STATUS_SOURCE = f"{CONTROL_SOURCE_PREFIX}get_josie_maintainer_status"
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
    r"how much (?:disk |storage )?space|space (?:is )?left on [cd](?: drive)?|"
    r"are (?:the )?(?:local )?services (?:ok|healthy|running|available)|"
    r"are (?:the )?backups (?:ok|healthy|current|recent)|"
    r"how many proposals (?:are )?(?:pending|awaiting review)|"
    r"what (?:safety |security )?locks are (?:active|enabled|on))\b",
    re.IGNORECASE,
)
PROPOSAL_REQUEST = re.compile(
    r"^\s*(?:(?:please|josie)[\s,]+|(?:can|could|would)\s+you\s+)*"
    r"(?:record|create|save|add|submit)\b",
    re.IGNORECASE,
)
PROPOSAL_KIND = re.compile(
    r"\b(?:health[_ -]?check|memory[_ -]?export|restore[_ -]?drill)\b",
    re.IGNORECASE,
)
PROPOSAL_NEGATION = re.compile(
    r"\b(?:do\s+not|don't|never)\s+(?:record|create|save|add|submit)\b",
    re.IGNORECASE,
)
PROVIDER_MARKERS = {
    "codex": re.compile(
        r"(?im)^[ \t]*(?:(?:please|josie|can you|could you|would you)[\s,]+)*"
        r"(?:ask|consult)\s+(?:the\s+)?codex(?:\s+cli)?\b\s*(?::|-)?\s*"
    ),
    "gemini": re.compile(
        r"(?im)^[ \t]*(?:(?:please|josie|can you|could you|would you)[\s,]+)*"
        r"(?:ask|consult)\s+(?:the\s+)?gemini(?:\s+cli)?\b\s*(?::|-)?\s*"
    ),
}
STATE_QUERY = re.compile(
    r"\b(?:current facts?|codex (?:cli )?(?:available|installed|working)|"
    r"gemini (?:cli )?(?:available|installed|working)|summit|groq|"
    r"consultant (?:response|result|decision)s? (?:are )?(?:stored|saved|persisted)|"
    r"tests? (?:all )?(?:pass|passed|passing|green)|test (?:count|result)|"
    r"complete (?:chatgpt|gemini) history|unified history importer|"
    r"history importer (?:built|exists|available))\b",
    re.IGNORECASE,
)
RECALL_QUERY = re.compile(
    r"\b(?:local memory|local history|search your own .*memory|"
    r"what (?:did|have) (?:we|you) (?:discuss|decide|remember))\b",
    re.IGNORECASE,
)
MAINTAINER_PREFIX = re.compile(r"(?im)^\s*Maintainer\s+Mode\s*:")
MAINTAINER_STATUS_QUERY = re.compile(
    r"\b(?:maintainer mode status|maintenance capability status)\b", re.IGNORECASE
)
MAINTAINER_REPLACEMENT = re.compile(
    r"(?is)^\s*Maintainer\s+Mode\s*:\s*in\s+([A-Za-z0-9_.\\/-]+)\s*,?\s*"
    r"replace\s+[\"“](.*?)[\"”]\s+with\s+[\"“](.*?)[\"”]"
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


def _proposal_requested(user_text: str) -> bool:
    return bool(
        PROPOSAL_REQUEST.search(user_text)
        and re.search(r"\bproposal\b", user_text, re.IGNORECASE)
        and PROPOSAL_KIND.search(user_text)
        and not PROPOSAL_NEGATION.search(user_text)
    )


def _explicit_query(user_text: str, provider: str) -> str | None:
    marker = PROVIDER_MARKERS[provider].search(user_text)
    if marker is None:
        return None
    tail = user_text[marker.end() :].lstrip()
    tail = re.sub(
        r"^independently(?:\s+with\s+the\s+same\s+question)?\s*:?[\s\r\n]*",
        "",
        tail,
        flags=re.IGNORECASE,
    )
    if tail.lower().startswith("to "):
        tail = tail[3:].lstrip()
    quote_pairs = {'"': '"', "“": "”", "'": "'"}
    if tail[:1] in quote_pairs:
        closing = quote_pairs[tail[0]]
        end = tail.find(closing, 1)
        if end > 1:
            return tail[1:end].strip()
    boundary = re.search(r"(?im)^\s*TEST\s+\d+\b", tail)
    query = tail[: boundary.start()] if boundary else tail
    query = query.strip().strip('"“”')
    return query if query else user_text.strip()


def _explicit_consultations(user_text: str) -> dict[str, str]:
    return {
        provider: query
        for provider in ("codex", "gemini")
        if (query := _explicit_query(user_text, provider)) is not None
    }


def _maintenance_directive(user_text: str) -> dict[str, str] | None:
    match = MAINTAINER_REPLACEMENT.search(user_text)
    if match is None:
        return None
    path, old_text, new_text = (item.strip() for item in match.groups())
    if not path or not old_text or not new_text:
        return None
    if len(user_text) > 8_000 or len(old_text) > 20_000 or len(new_text) > 20_000:
        return None
    return {
        "path": path.replace("\\", "/"),
        "old_text": old_text,
        "new_text": new_text,
    }


def _recall_query(user_text: str) -> str:
    section = re.search(
        r"(?is)TEST\s+3\b.*?\banswer\s*:\s*[\"“](.*?)[\"”]",
        user_text,
    )
    if section is not None and section.group(1).strip():
        return section.group(1).strip()[:2_000]
    if len(user_text) <= 2_000:
        return user_text
    match = RECALL_QUERY.search(user_text)
    start = max(0, (match.start() if match else 0) - 300)
    return user_text[start : start + 2_000]


def _trusted_source_message(body: dict, user_text: str) -> str | None:
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
        if source_name == STATUS_SOURCE and not STATUS_QUERY.search(user_text):
            continue
        if source_name == PROPOSAL_SOURCE and not _proposal_requested(user_text):
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


def _last_assistant_text(body: dict) -> str:
    for message in reversed(body.get("messages") or []):
        if isinstance(message, dict) and message.get("role") == "assistant":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def _connection_token(connection_id: str) -> str:
    connections = json.loads(os.environ.get("TOOL_SERVER_CONNECTIONS", "[]"))
    connection = next(
        (
            item
            for item in connections
            if (item.get("info") or {}).get("id") == connection_id
        ),
        None,
    )
    if not isinstance(connection, dict) or not isinstance(connection.get("key"), str):
        raise ValueError("private local credential is unavailable")
    return connection["key"]


def _status_token() -> str:
    return _connection_token(CONNECTION_ID)


def _control_post(path: str, payload: dict, *, timeout: int = 100) -> dict:
    encoded = json.dumps(payload).encode("utf-8")
    request = Request(
        CONTROL_URL + path,
        data=encoded,
        headers={
            "Authorization": f"Bearer {_connection_token(CONTROL_CONNECTION_ID)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError("local conversation control rejected the request")
        raw = response.read(65_537)
    if len(raw) > 65_536:
        raise ValueError("local conversation control response exceeds size limit")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("local conversation control response is invalid")
    return result


def _consultation_request_id(body: dict, provider: str, query: str) -> str:
    metadata = body.get("metadata") or {}
    scope = str(
        body.get("chat_id")
        or metadata.get("chat_id")
        or body.get("id")
        or metadata.get("message_id")
        or "openwebui"
    )
    digest = hashlib.sha256(
        f"{scope}\0{provider}\0{query}".encode("utf-8")
    ).hexdigest()
    return f"openwebui-{provider}-{digest[:32]}"


def _consultation_payload(body: dict, provider: str, query: str) -> dict:
    return {
        "query": query,
        "request_id": _consultation_request_id(body, provider, query),
    }


def _maintenance_request_id(body: dict, user_text: str) -> str:
    metadata = body.get("metadata") or {}
    scope = str(
        body.get("chat_id")
        or metadata.get("chat_id")
        or body.get("id")
        or metadata.get("message_id")
        or "openwebui"
    )
    digest = hashlib.sha256(f"{scope}\0{user_text}".encode("utf-8")).hexdigest()
    return f"openwebui-maintainer-{digest[:32]}"


def _maintenance_payload(body: dict, user_text: str, directive: dict[str, str]) -> dict:
    return {
        "request_id": _maintenance_request_id(body, user_text),
        "user_request": user_text,
        "path": directive["path"],
        "old_text": directive["old_text"],
        "new_text": directive["new_text"],
    }


def _prefetch_consultations(body: dict, directives: dict[str, str]) -> None:
    def invoke(item: tuple[str, str]) -> None:
        provider, query = item
        _control_post(
            f"/v1/consult/{provider}",
            _consultation_payload(body, provider, query),
        )

    with ThreadPoolExecutor(max_workers=len(directives)) as executor:
        futures = [executor.submit(invoke, item) for item in directives.items()]
        for future in futures:
            try:
                future.result()
            except Exception:
                pass


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


def _all_sources(body: dict) -> list[dict]:
    candidates = []
    candidates.extend(body.get("sources") or [])
    candidates.extend((body.get("metadata") or {}).get("sources") or [])
    for message in body.get("messages") or []:
        if isinstance(message, dict):
            candidates.extend(message.get("sources") or [])
    return [item for item in candidates if isinstance(item, dict)]


def _evidence_source(name: str, payload: dict) -> dict:
    return {
        "source": {"name": name},
        "document": [json.dumps(payload, ensure_ascii=False, sort_keys=True)],
        "metadata": [{"source": name}],
        "tool_result": True,
    }


def _consultation_message(provider: str, payload: dict) -> str:
    expected = f"{provider}_cli"
    if (
        payload.get("provider") != expected
        or not isinstance(payload.get("request_id"), str)
        or payload.get("persisted_locally") is not True
        or payload.get("captured_response_is_exact") is not True
        or payload.get("api_key_used") is not False
        or payload.get("actions_executed") != 0
    ):
        raise ValueError(f"{provider} consultation evidence is invalid")
    label = provider.upper()
    if payload.get("status") == "ok" and isinstance(payload.get("response"), str):
        response = payload["response"]
        if not response or len(response) > 16_000:
            raise ValueError(f"{provider} consultation response is invalid")
        return f"{label} — ACTUAL CONSULTANT RESULT\n\n{response}"
    error = payload.get("error")
    if payload.get("status") != "unavailable" or not isinstance(error, str) or not error:
        raise ValueError(f"{provider} consultation failure evidence is invalid")
    return (
        f"{label} — CONSULTATION UNAVAILABLE\n\n{error}\n\n"
        "Josie remains available through local Ollama."
    )


def _state_message(payload: dict) -> str:
    required_false = (
        "summit_groq_active",
        "complete_chatgpt_history_imported",
        "complete_gemini_history_imported",
        "unified_history_importer_built",
    )
    if (
        payload.get("status") != "ok"
        or payload.get("source") != "machine_config_and_local_sqlite"
        or payload.get("default_provider") != "local_ollama"
        or payload.get("consultant_results_persisted_locally") is not True
        or any(payload.get(name) is not False for name in required_false)
        or payload.get("actions_executed") != 0
        or not isinstance(payload.get("assistant_message"), str)
    ):
        raise ValueError("deterministic state evidence is invalid")
    return str(payload["assistant_message"])


def _recall_message(payload: dict) -> str:
    if (
        payload.get("status") != "ok"
        or payload.get("source") != "local_sqlite"
        or payload.get("cloud_activity") is not False
        or payload.get("actions_executed") != 0
        or not isinstance(payload.get("matches"), list)
    ):
        raise ValueError("local recall evidence is invalid")
    lines = [
        "LOCAL MEMORY — ACTUAL SQLITE MATCHES",
        "Historical conversation text is not current-machine proof.",
    ]
    for match in payload["matches"][:4]:
        if not isinstance(match, dict):
            continue
        reference = match.get("reference")
        content = match.get("content")
        if isinstance(reference, str) and isinstance(content, str):
            lines.append(f"- {reference}: {content}")
    if len(lines) == 2:
        lines.append("- No matching local record was found.")
    return "\n\n".join(lines[:2]) + "\n" + "\n".join(lines[2:])


def _maintenance_message(payload: dict) -> str:
    if (
        payload.get("status")
        not in {"completed", "rolled_back", "blocked", "approval_required"}
        or not isinstance(payload.get("request_id"), str)
        or payload.get("local_only") is not True
        or payload.get("arbitrary_shell_available") is not False
        or payload.get("push_performed") is not False
        or payload.get("new_database") is not False
        or payload.get("new_container") is not False
        or not isinstance(payload.get("actions_executed"), int)
        or not isinstance(payload.get("assistant_message"), str)
    ):
        raise ValueError("Maintainer evidence is invalid")
    if payload["status"] == "completed":
        tests = payload.get("tests") or {}
        if (
            tests.get("status") != "passed"
            or not isinstance(payload.get("final_commit"), str)
            or not payload.get("final_commit")
            or payload.get("approval_required") is not False
            or not isinstance(payload.get("files_changed"), list)
            or len(payload["files_changed"]) != 1
        ):
            raise ValueError("Completed Maintainer evidence is invalid")
    if payload["status"] == "approval_required" and payload.get("approval_required") is not True:
        raise ValueError("Maintainer approval evidence is invalid")
    return str(payload["assistant_message"])


def _maintainer_status_message(payload: dict) -> str:
    if (
        payload.get("status") != "ok"
        or payload.get("mode") != "maintainer_0_1"
        or payload.get("enabled") is not True
        or payload.get("arbitrary_shell_available") is not False
        or payload.get("package_install_allowed") is not False
        or payload.get("push_allowed") is not False
        or payload.get("consultants_are_advisory_only") is not True
    ):
        raise ValueError("Maintainer status evidence is invalid")
    git = payload.get("git") or {}
    return "\n".join(
        (
            "JOSIE MAINTAINER — ACTUAL CONTROL-PLANE STATUS",
            "Mode: maintainer_0_1; enabled=true.",
            f"Git branch: {git.get('branch', 'unknown')}.",
            f"Git commit: {git.get('commit', 'unknown')}.",
            "Arbitrary shell: unavailable.",
            "Package installation: not allowed.",
            "Remote push: not allowed.",
            "Consultants: advisory only; their failure grants no authority.",
        )
    )


def _authoritative_response(body: dict, user_text: str) -> tuple[str, list[dict], str] | None:
    maintenance = _maintenance_directive(user_text)
    if MAINTAINER_PREFIX.search(user_text):
        if maintenance is None:
            return (
                'JOSIE MAINTAINER — REQUEST REJECTED\n\nUse exactly: Maintainer Mode: '
                'in <path> replace "<exact old text>" with "<exact new text>".',
                [],
                "local_maintainer_rejected",
            )
        try:
            payload = _control_post(
                "/v1/maintainer/replace",
                _maintenance_payload(body, user_text, maintenance),
                timeout=300,
            )
            return (
                _maintenance_message(payload),
                [_evidence_source(MAINTAINER_SOURCE, payload)],
                "local_maintainer",
            )
        except Exception as exc:
            return (
                "JOSIE MAINTAINER — CONTROL SERVICE UNAVAILABLE\n\n"
                f"No unverified success is claimed. Error: {type(exc).__name__}.",
                [],
                "local_maintainer_failed_closed",
            )

    if MAINTAINER_STATUS_QUERY.search(user_text):
        try:
            payload = _control_post(
                "/v1/maintainer/status", {"query": user_text}, timeout=10
            )
            return (
                _maintainer_status_message(payload),
                [_evidence_source(MAINTAINER_STATUS_SOURCE, payload)],
                "local_maintainer_status",
            )
        except Exception as exc:
            return (
                "JOSIE MAINTAINER — STATUS UNAVAILABLE\n\n"
                f"Local evidence service error: {type(exc).__name__}.",
                [],
                "local_maintainer_status_unavailable",
            )

    directives = _explicit_consultations(user_text)
    state_requested = bool(STATE_QUERY.search(user_text))
    recall_requested = bool(RECALL_QUERY.search(user_text))
    if not directives and not state_requested and not recall_requested:
        return None

    parts: list[str] = []
    sources: list[dict] = []
    routes: list[str] = []
    for provider, query in directives.items():
        source_name = CODEX_SOURCE if provider == "codex" else GEMINI_SOURCE
        try:
            payload = _control_post(
                f"/v1/consult/{provider}",
                _consultation_payload(body, provider, query),
            )
            parts.append(_consultation_message(provider, payload))
            sources.append(_evidence_source(source_name, payload))
            routes.append(f"{provider}_cli")
        except Exception as exc:
            parts.append(
                f"{provider.upper()} — CONSULTATION UNAVAILABLE\n\n"
                f"Local evidence service error: {type(exc).__name__}.\n\n"
                "Josie remains available through local Ollama."
            )

    if recall_requested:
        try:
            payload = _control_post(
                "/v1/recall", {"query": _recall_query(user_text)}, timeout=10
            )
            parts.append(_recall_message(payload))
            sources.append(_evidence_source(RECALL_SOURCE, payload))
        except Exception as exc:
            parts.append(
                "LOCAL MEMORY — UNAVAILABLE\n\n"
                f"Local evidence service error: {type(exc).__name__}."
            )

    if state_requested:
        try:
            payload = _control_post("/v1/state", {"query": user_text}, timeout=10)
            parts.append(_state_message(payload))
            sources.append(_evidence_source(STATE_SOURCE, payload))
        except Exception as exc:
            parts.append(
                "DETERMINISTIC JOSIE STATE — UNAVAILABLE\n\n"
                f"Local evidence service error: {type(exc).__name__}."
            )

    route = "+".join(routes) if routes else "local_evidence"
    return "\n\n".join(parts), sources, route


def _conversation_route(body: dict) -> str:
    source_names = {
        (source.get("source") or {}).get("name") for source in _all_sources(body)
    }
    if CODEX_SOURCE in source_names:
        return "codex_cli"
    if GEMINI_SOURCE in source_names:
        return "gemini_cli"
    if MAINTAINER_SOURCE in source_names:
        return "local_maintainer"
    return "local_ollama"


def _history_event_id(body: dict, role: str) -> str:
    metadata = body.get("metadata") or {}
    values = (
        body.get("chat_id"),
        body.get("id"),
        metadata.get("chat_id"),
        metadata.get("message_id"),
        role,
    )
    return ":".join(str(value) for value in values if value)


def _record_history(body: dict, *, role: str, content: str, route: str) -> None:
    if not content or len(content) > 16_000:
        return
    payload = json.dumps(
        {
            "role": role,
            "content": content,
            "route": route,
            "event_id": _history_event_id(body, role),
        }
    ).encode("utf-8")
    request = Request(
        HISTORY_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {_connection_token(CONTROL_CONNECTION_ID)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=1) as response:
        if response.status != 200:
            raise ValueError("local conversation history service rejected the request")
        response.read(1_024)


def _replace_last_assistant(body: dict, content: str) -> dict:
    messages = list(body.get("messages") or [])
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "assistant":
            messages[index] = {**message, "content": content}
            return {**body, "messages": messages}
    raise ValueError("assistant response is unavailable")


def _attach_sources(body: dict, sources: list[dict]) -> dict:
    if not sources:
        return body
    combined = [*_all_sources(body), *sources]
    messages = list(body.get("messages") or [])
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "assistant":
            messages[index] = {**message, "sources": combined}
            break
    return {**body, "sources": combined, "messages": messages}


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=-100)

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __model__: dict | None = None) -> dict:
        """Enable memory and prefetch explicit consultants without model routing."""
        model_id = body.get("model") or ((__model__ or {}).get("id"))
        if model_id != MODEL_ID:
            return body
        features = dict(body.get("features") or {})
        features["memory"] = True
        updated = {**body, "features": features}
        user_text = _last_user_text(updated)
        explicit = _explicit_consultations(user_text)
        maintenance = bool(
            MAINTAINER_PREFIX.search(user_text)
            or MAINTAINER_STATUS_QUERY.search(user_text)
        )
        deterministic = bool(
            STATE_QUERY.search(user_text)
            or RECALL_QUERY.search(user_text)
            or maintenance
        )
        if explicit:
            _prefetch_consultations(updated, explicit)
        if explicit or deterministic:
            blocked_ids = {
                CONTROL_CONNECTION_ID,
                f"server:{CONTROL_CONNECTION_ID}",
            }
            if deterministic:
                blocked_ids.update({CONNECTION_ID, f"server:{CONNECTION_ID}"})
            updated["tool_ids"] = [
                tool_id
                for tool_id in updated.get("tool_ids") or []
                if tool_id not in blocked_ids
            ]
        try:
            _record_history(
                updated,
                role="user",
                content=_last_user_text(updated),
                route="local_ollama",
            )
        except Exception:
            pass
        return updated

    def outlet(self, body: dict, __model__: dict | None = None) -> dict:
        model_id = body.get("model") or ((__model__ or {}).get("id"))
        if model_id != MODEL_ID:
            return body

        user_text = _last_user_text(body)
        authoritative = _authoritative_response(body, user_text)
        if authoritative is not None:
            trusted, sources, route = authoritative
            updated = _attach_sources(_replace_last_assistant(body, trusted), sources)
        else:
            trusted = _trusted_source_message(body, user_text)
            if trusted is None and STATUS_QUERY.search(user_text):
                trusted = _fresh_status_message()
            updated = _replace_last_assistant(body, trusted) if trusted is not None else body
            route = _conversation_route(updated)
        try:
            _record_history(
                updated,
                role="assistant",
                content=_last_assistant_text(updated),
                route=route,
            )
        except Exception:
            pass
        return updated

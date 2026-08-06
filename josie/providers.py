"""Minimal HTTPS provider probes. Keys are never returned or logged."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Config


def provider_status(config: Config) -> dict[str, object]:
    return {
        "status": "ok",
        "cloud_calls_allowed": config.allow_cloud,
        "openai": {"configured": bool(config.openai_api_key), "model": config.openai_model},
        "gemini": {"configured": bool(config.gemini_api_key), "model": config.gemini_model},
    }


def _post(url: str, headers: dict[str, str], payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Provider returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Provider connection failed: {exc.reason}") from exc


def probe_openai(config: Config) -> dict[str, object]:
    if not config.allow_cloud:
        raise RuntimeError("Cloud API calls are disabled by JOSIE_ALLOW_CLOUD=false")
    if not config.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    data = _post(
        "https://api.openai.com/v1/responses",
        {"Authorization": f"Bearer {config.openai_api_key}"},
        {
            "model": config.openai_model,
            "input": "Reply with exactly: OK",
            "max_output_tokens": 16,
            "store": False,
        },
    )
    return {"status": "ok", "provider": "openai", "model": data.get("model", config.openai_model)}


def probe_gemini(config: Config) -> dict[str, object]:
    if not config.allow_cloud:
        raise RuntimeError("Cloud API calls are disabled by JOSIE_ALLOW_CLOUD=false")
    if not config.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    data = _post(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        {"x-goog-api-key": config.gemini_api_key},
        {
            "model": config.gemini_model,
            "input": "Reply with exactly: OK",
            "store": False,
            "generation_config": {"max_output_tokens": 16, "thinking_level": "low"},
        },
    )
    return {"status": "ok", "provider": "gemini", "model": data.get("model", config.gemini_model)}

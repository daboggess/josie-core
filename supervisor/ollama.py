from __future__ import annotations

import json
import urllib.error
import urllib.request


def get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def preflight(base_url: str, model: str) -> dict:
    try:
        tags = get_json(base_url.rstrip("/") + "/api/tags")
        try:
            loaded = get_json(base_url.rstrip("/") + "/api/ps")
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            loaded = {"models": [], "supported": False}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": "PREFLIGHT_MISSING_RUNTIME", "error": str(exc)}
    matches = [item for item in tags.get("models", []) if item.get("name") == model or item.get("model") == model]
    if not matches:
        return {"ok": False, "reason": "PREFLIGHT_MISSING_MODEL", "available": [x.get("name") for x in tags.get("models", [])]}
    return {"ok": True, "reason": "OK", "discovered_model": matches[0], "loaded_models": loaded.get("models", [])}

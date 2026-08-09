"""Authenticated client for the isolated read-only research connector."""

from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request

from .browser_policy import load_browser_policy, validate_research_url
from .config import Config


def extract_official_source(*, config: Config, project_root: Path, url: str) -> dict[str, object]:
    policy = load_browser_policy(project_root)
    approved_url = validate_research_url(policy, url)
    if config.external_storage is None:
        raise RuntimeError("External storage is required for the protected browser credential")
    token_path = config.external_storage / "secrets" / "browser-token.txt"
    token = token_path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("Browser credential is missing or invalid")

    request = urllib.request.Request(
        "http://127.0.0.1:3010/extract",
        data=json.dumps({"url": approved_url}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(131_072)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"Research connector rejected the request ({exc.code}): {detail}") from exc
    result = json.loads(body.decode("utf-8"))
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise RuntimeError("Research connector returned an invalid response")
    required = {
        "content_untrusted": True,
        "scripts_stripped": True,
        "hidden_text_stripped": True,
        "forms_submitted": False,
        "downloads_saved": False,
        "cookies_used": False,
        "model_direct_access": False,
        "external_activity": True,
    }
    if any(result.get(name) is not expected for name, expected in required.items()):
        raise RuntimeError("Research connector safety attestation is invalid")
    result["credential_exposed"] = False
    return result

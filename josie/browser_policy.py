"""Fail-closed policy reader for the disabled browser worker."""

from __future__ import annotations

import json
from pathlib import Path


CAPABILITIES = {"navigation", "extraction", "form_entry", "downloads", "uploads"}
REQUIRED_NETWORK_CONTROLS = {
    "block_loopback", "block_private_ranges", "block_tailscale_ranges",
    "block_off_allowlist_redirects",
}
REQUIRED_CONTENT_CONTROLS = {
    "treat_page_content_as_untrusted", "strip_hidden_text_before_model_review",
    "strip_scripts_before_model_review",
}
REQUIRED_PROHIBITIONS = {
    "bypass_access_controls", "bypass_captcha", "bypass_anti_bot",
    "human_impersonation", "credential_exfiltration", "model_direct_execution",
}


def load_browser_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "browser-policy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1 or raw.get("default") != "deny":
        raise ValueError("Browser policy must use schema 1 and default deny")
    if raw.get("enabled") is not False:
        raise ValueError("Browser execution is not implemented and must remain disabled")
    hosts = raw.get("allowed_hosts")
    if not isinstance(hosts, list) or hosts:
        raise ValueError("Browser allowlist must remain empty until attended approval")
    if raw.get("prefer_dedicated_connectors") is not True:
        raise ValueError("Browser policy must prefer dedicated connectors")
    capabilities = raw.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != CAPABILITIES:
        raise ValueError("Browser capabilities are incomplete")
    if any(value is not False for value in capabilities.values()):
        raise ValueError("All browser capabilities must remain disabled")
    network = raw.get("network_controls")
    if not isinstance(network, dict) or set(network) != REQUIRED_NETWORK_CONTROLS:
        raise ValueError("Browser network controls are incomplete")
    if any(value is not True for value in network.values()):
        raise ValueError("All browser network blocks must remain enabled")
    content = raw.get("content_controls")
    if not isinstance(content, dict) or set(content) != REQUIRED_CONTENT_CONTROLS:
        raise ValueError("Browser content controls are incomplete")
    if any(value is not True for value in content.values()):
        raise ValueError("All browser content controls must remain enabled")
    prohibited = raw.get("prohibited")
    if not isinstance(prohibited, list) or set(prohibited) != REQUIRED_PROHIBITIONS:
        raise ValueError("Browser prohibitions are incomplete")
    return {
        "status": "locked",
        "enabled": False,
        "default": "deny",
        "allowed_hosts": [],
        "allowed_host_count": 0,
        "prefer_dedicated_connectors": True,
        "capabilities": capabilities,
        "network_controls": network,
        "content_controls": content,
        "prohibited": prohibited,
        "external_activity": False,
    }

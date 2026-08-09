"""Fail-closed policy reader for Josie's bounded research connector."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit


CAPABILITIES = {"navigation", "extraction", "form_entry", "downloads", "uploads"}
REQUIRED_NETWORK_CONTROLS = {
    "block_loopback", "block_private_ranges", "block_tailscale_ranges",
    "block_off_allowlist_redirects", "resolve_and_validate_every_connection",
}
REQUIRED_CONTENT_CONTROLS = {
    "treat_page_content_as_untrusted", "strip_hidden_text_before_model_review",
    "strip_scripts_before_model_review", "model_direct_access",
    "persist_page_content", "javascript_execution", "cookies_enabled",
}
REQUIRED_PROHIBITIONS = {
    "bypass_access_controls", "bypass_captcha", "bypass_anti_bot",
    "human_impersonation", "credential_exfiltration", "model_direct_execution",
}


def _hostname(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Browser hostnames must be strings")
    host = value.strip().lower()
    if not host or "*" in host or ":" in host or "/" in host or host.startswith("."):
        raise ValueError("Browser hostnames must be exact DNS names without wildcards")
    return host


def _future_expiration(value: object) -> tuple[str, bool]:
    if not isinstance(value, str):
        raise ValueError("Browser pilot expiration is missing")
    expiration = datetime.fromisoformat(value)
    if expiration.tzinfo is None:
        raise ValueError("Browser pilot expiration must include a timezone")
    return value, datetime.now(timezone.utc) >= expiration.astimezone(timezone.utc)


def load_browser_policy(project_root: Path) -> dict[str, object]:
    path = project_root / "config" / "browser-policy.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 2 or raw.get("default") != "deny":
        raise ValueError("Browser policy must use schema 2 and default deny")
    if raw.get("mode") != "read_only_research" or raw.get("enabled") is not True:
        raise ValueError("Only the approved read-only research mode may be enabled")
    if raw.get("prefer_dedicated_connectors") is not True:
        raise ValueError("Browser policy must prefer dedicated connectors")

    hosts_raw = raw.get("allowed_hosts")
    if not isinstance(hosts_raw, list) or not hosts_raw:
        raise ValueError("Browser pilot requires an explicit nonempty hostname allowlist")
    hosts = [_hostname(value) for value in hosts_raw]
    if len(hosts) != len(set(hosts)):
        raise ValueError("Browser allowlist contains duplicate hostnames")

    urls_raw = raw.get("allowed_urls")
    if not isinstance(urls_raw, list) or not urls_raw:
        raise ValueError("Browser pilot requires exact URL allowlisting")
    allowed_urls: list[str] = []
    for value in urls_raw:
        if not isinstance(value, str):
            raise ValueError("Allowed URLs must be strings")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or (parsed.hostname or "").lower() not in hosts
            or parsed.fragment
        ):
            raise ValueError("Allowed URLs must be exact credential-free HTTPS URLs")
        allowed_urls.append(parsed.geturl())
    if len(allowed_urls) != len(set(allowed_urls)):
        raise ValueError("Browser allowlist contains duplicate URLs")

    paths_raw = raw.get("allowed_paths")
    if not isinstance(paths_raw, dict) or set(paths_raw) != set(hosts):
        raise ValueError("Every allowed host must have an exact path allowlist")
    allowed_paths: dict[str, list[str]] = {}
    for host, values in paths_raw.items():
        if not isinstance(values, list) or not values:
            raise ValueError("Every allowed host requires at least one path")
        clean_paths: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.startswith("/") or "*" in value:
                raise ValueError("Allowed paths must be absolute and wildcard-free")
            clean_paths.append(value)
        allowed_paths[host] = clean_paths

    capabilities = raw.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != CAPABILITIES:
        raise ValueError("Browser capabilities are incomplete")
    if capabilities.get("navigation") is not True or capabilities.get("extraction") is not True:
        raise ValueError("The pilot requires only navigation and extraction")
    if any(capabilities.get(name) is not False for name in ("form_entry", "downloads", "uploads")):
        raise ValueError("Browser write, download, and upload capabilities must remain disabled")

    limits = raw.get("request_limits")
    if not isinstance(limits, dict):
        raise ValueError("Browser request limits are missing")
    if limits.get("allowed_schemes") != ["https"] or limits.get("allowed_ports") != [443]:
        raise ValueError("Browser pilot must use HTTPS on port 443 only")
    if not isinstance(limits.get("allowed_content_types"), list) or not limits["allowed_content_types"]:
        raise ValueError("Browser content-type allowlist is missing")
    numeric_bounds = {
        "max_redirects": (0, 5),
        "max_response_bytes": (1, 2_000_000),
        "max_output_characters": (1, 50_000),
        "request_timeout_seconds": (1, 30),
        "requests_per_minute": (1, 12),
        "parallel_requests": (1, 1),
    }
    for name, (minimum, maximum) in numeric_bounds.items():
        value = limits.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
            raise ValueError(f"Browser request limit is unsafe: {name}")

    network = raw.get("network_controls")
    if not isinstance(network, dict) or set(network) != REQUIRED_NETWORK_CONTROLS:
        raise ValueError("Browser network controls are incomplete")
    if any(value is not True for value in network.values()):
        raise ValueError("All browser network blocks must remain enabled")
    content = raw.get("content_controls")
    if not isinstance(content, dict) or set(content) != REQUIRED_CONTENT_CONTROLS:
        raise ValueError("Browser content controls are incomplete")
    required_true = {
        "treat_page_content_as_untrusted", "strip_hidden_text_before_model_review",
        "strip_scripts_before_model_review",
    }
    if any(content.get(name) is not True for name in required_true):
        raise ValueError("Untrusted-content controls must remain enabled")
    required_false = {
        "model_direct_access", "persist_page_content", "javascript_execution", "cookies_enabled",
    }
    if any(content.get(name) is not False for name in required_false):
        raise ValueError("Model, persistence, JavaScript, and cookie access must remain disabled")
    prohibited = raw.get("prohibited")
    if not isinstance(prohibited, list) or set(prohibited) != REQUIRED_PROHIBITIONS:
        raise ValueError("Browser prohibitions are incomplete")

    pilot = raw.get("pilot")
    if not isinstance(pilot, dict):
        raise ValueError("Browser pilot metadata is missing")
    for name in ("name", "purpose", "approved_by", "approved_on", "credential_rule", "retention_rule"):
        if not isinstance(pilot.get(name), str) or not pilot[name].strip():
            raise ValueError(f"Browser pilot metadata is missing: {name}")
    expires_at, expired = _future_expiration(pilot.get("expires_at"))

    return {
        "status": "expired" if expired else "read_only_pilot",
        "enabled": not expired,
        "default": "deny",
        "mode": "read_only_research",
        "pilot": {**pilot, "expires_at": expires_at, "expired": expired},
        "allowed_hosts": hosts,
        "allowed_urls": allowed_urls,
        "allowed_paths": allowed_paths,
        "allowed_host_count": len(hosts),
        "prefer_dedicated_connectors": True,
        "capabilities": capabilities,
        "request_limits": limits,
        "network_controls": network,
        "content_controls": content,
        "prohibited": prohibited,
        "write_actions_locked": True,
        "model_direct_access": False,
        "external_activity": False,
    }


def validate_research_url(policy: dict[str, object], value: str) -> str:
    """Validate a requested URL against the exact host and path allowlists."""
    if policy.get("status") != "read_only_pilot" or policy.get("enabled") is not True:
        raise ValueError("The browser research pilot is locked or expired")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or parsed.port not in (None, 443):
        raise ValueError("Research URLs must use HTTPS on port 443")
    if parsed.username or parsed.password:
        raise ValueError("Credentials are forbidden in research URLs")
    host = (parsed.hostname or "").lower()
    hosts = policy.get("allowed_hosts")
    if not isinstance(hosts, list) or host not in hosts:
        raise ValueError("Research URL hostname is not allowlisted")
    paths = policy.get("allowed_paths")
    if not isinstance(paths, dict) or not isinstance(paths.get(host), list):
        raise ValueError("Research URL has no approved path rules")
    if not any(parsed.path == prefix for prefix in paths[host]):
        raise ValueError("Research URL path is not allowlisted")
    normalized = parsed.geturl()
    urls = policy.get("allowed_urls")
    if not isinstance(urls, list) or normalized not in urls:
        raise ValueError("Research URL is not exactly allowlisted")
    return normalized

"""Direct Playwright transport for the bounded Summit Relay v0.1 exchange."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from josie.summit_relay import AcceptanceRelay, ReceiptLog, load_relay_config


BROWSER_CONFIG_KEYS = {
    "schema_version", "transport", "chrome_executable", "profile_directory",
    "headless", "navigation_timeout_ms", "providers", "josie_http",
}
PROVIDER_KEYS = {"url", "composer", "send", "stop", "assistant", "login"}
JOSIE_HTTP_KEYS = {
    "base_url", "model", "completion_path", "completed_path", "filter_ids",
    "tool_ids", "timeout_seconds",
}
def load_browser_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "summit-browser.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Summit browser configuration is missing or invalid") from exc
    if not isinstance(config, dict) or set(config) != BROWSER_CONFIG_KEYS:
        raise ValueError("Summit browser configuration has unexpected fields")
    if config["schema_version"] != 1 or config["transport"] != "direct_playwright":
        raise ValueError("Summit browser configuration version is unsupported")
    if type(config["headless"]) is not bool:
        raise ValueError("Summit browser headless setting must be Boolean")
    timeout = config["navigation_timeout_ms"]
    if type(timeout) is not int or not 10_000 <= timeout <= 120_000:
        raise ValueError("Summit browser navigation timeout is invalid")
    providers = config["providers"]
    if not isinstance(providers, dict) or set(providers) != {"sophie", "bernie"}:
        raise ValueError("Summit browser must configure exactly ChatGPT and Gemini")
    for name, provider in providers.items():
        if not isinstance(provider, dict) or set(provider) != PROVIDER_KEYS:
            raise ValueError(f"Summit browser provider {name} is invalid")
        if not isinstance(provider["url"], str) or not provider["url"].startswith(("https://", "http://127.0.0.1:")):
            raise ValueError(f"Summit browser provider {name} URL is invalid")
        for selector_key in PROVIDER_KEYS - {"url"}:
            values = provider[selector_key]
            if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
                raise ValueError(f"Summit browser provider {name} selectors are invalid")
    http = config["josie_http"]
    if not isinstance(http, dict) or set(http) != JOSIE_HTTP_KEYS:
        raise ValueError("Summit Josie HTTP configuration is invalid")
    if http["base_url"] != "http://127.0.0.1:3000":
        raise ValueError("Summit Josie HTTP delivery must remain loopback-local")
    if http["model"] != "josie-qwen3-8b:1.0":
        raise ValueError("Summit Josie HTTP model is invalid")
    if http["completion_path"] != "/api/chat/completions" or http["completed_path"] != "/api/chat/completed":
        raise ValueError("Summit Josie HTTP paths are invalid")
    if http["tool_ids"] != [] or http["filter_ids"] != ["josie_exact_tool_response"]:
        raise ValueError("Summit Josie HTTP delivery must be ordinary non-tool chat")
    if type(http["timeout_seconds"]) is not int or not 30 <= http["timeout_seconds"] <= 300:
        raise ValueError("Summit Josie HTTP timeout is invalid")
    return config


def initialize_profile(*, project_root: Path) -> Path:
    """Create an empty dedicated profile; never inspect or copy the primary profile."""
    config = load_browser_config(project_root)
    destination = project_root / config["profile_directory"]
    destination.mkdir(parents=True, exist_ok=True)
    return destination


class DirectSummitBrowser:
    def __init__(self, *, project_root: Path, config: dict[str, Any]):
        self.project_root = project_root
        self.config = config
        self.profile_path = project_root / config["profile_directory"]
        self._playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.pages: dict[str, Page] = {}

    def __enter__(self) -> "DirectSummitBrowser":
        if not self.profile_path.is_dir():
            raise RuntimeError("Dedicated Summit browser profile is missing")
        executable = Path(self.config["chrome_executable"])
        if not executable.is_file():
            raise RuntimeError("Installed Google Chrome is unavailable")
        self._playwright = sync_playwright().start()
        browser = self._playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
        if not browser.contexts:
            raise RuntimeError("Summit Chrome has no browser context")
        self.context = browser.contexts[0]
        self.context.set_default_timeout(15_000)
        self.context.set_default_navigation_timeout(self.config["navigation_timeout_ms"])
        for worker, provider in self.config["providers"].items():
            target_url = provider["url"].rstrip("/")
            matches = [
                page for page in self.context.pages
                if page.url.rstrip("/").startswith(target_url)
            ]

            if matches:
                page = matches[-1]
            else:
                page = self.context.new_page()
                page.goto(provider["url"], wait_until="domcontentloaded")

            self.pages[worker] = page
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        # Summit Chrome is externally managed. Disconnect Playwright only;
        # do not close the authenticated browser context.
        if self._playwright is not None:
            self._playwright.stop()

    @staticmethod
    def _first(page: Page, selectors: list[str]):
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() > 0:
                return locator.first
        return None

    def authentication(self) -> dict[str, dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}
        for worker, page in self.pages.items():
            provider = self.config["providers"][worker]
            composer = self._first(page, provider["composer"])
            login_visible = any(
                page.locator(selector).count() > 0 and page.locator(selector).first.is_visible()
                for selector in provider["login"]
            )
            states[worker] = {
                "authenticated": composer is not None and composer.is_visible() and not login_visible,
                "composer_found": composer is not None and composer.is_visible(),
                "login_visible": login_visible,
                "url": page.url,
            }
        return states

    def _assistant_texts(self, worker: str) -> list[str]:
        page = self.pages[worker]
        for selector in self.config["providers"][worker]["assistant"]:
            values = [value.strip() for value in page.locator(selector).all_inner_texts() if value.strip()]
            if values:
                return values
        return []

    def send_and_capture(self, action: dict[str, Any]) -> dict[str, Any]:
        worker = action["worker"]
        page = self.pages[worker]
        provider = self.config["providers"][worker]
        base = {
            "action_id": action["action_id"], "tab_id": None,
            "page_url": page.url, "page_title": page.title(),
        }
        try:
            auth = self.authentication()[worker]
            if not auth["authenticated"]:
                raise RuntimeError("authentication_required")
            composer = self._first(page, provider["composer"])
            if composer is None:
                raise RuntimeError("composer_not_found")
            before = self._assistant_texts(worker)
            baseline = before[-1] if before else ""
            composer.fill(action["payload"])
            send = self._first(page, provider["send"])
            if send is None:
                raise RuntimeError("send_control_not_found")
            send.click()
            deadline = time.monotonic() + action["timeout_seconds"]
            candidate = ""
            stable_since = 0.0
            while time.monotonic() < deadline:
                texts = self._assistant_texts(worker)
                latest = texts[-1] if texts else ""
                changed = bool(latest and (len(texts) > len(before) or latest != baseline))
                generating = any(page.locator(s).count() > 0 and page.locator(s).first.is_visible() for s in provider["stop"])
                if changed:
                    if latest != candidate:
                        candidate, stable_since = latest, time.monotonic()
                    exact_ready = action["expected_exact"] is not None and latest == action["expected_exact"] and not generating
                    stable_ready = action["expected_exact"] is None and not generating and time.monotonic() - stable_since >= 2.5
                    if exact_ready or stable_ready:
                        return {**base, "ok": True, "assistant_text": latest, "error_code": "", "error_detail": ""}
                page.wait_for_timeout(500)
            raise RuntimeError("assistant_response_timeout")
        except Exception as exc:
            code = str(exc).splitlines()[0][:80] or type(exc).__name__
            return {
                **base, "ok": False, "assistant_text": "",
                "error_code": code, "error_detail": type(exc).__name__,
            }


def _openwebui_owner_token() -> str:
    script = (
        "import asyncio,os,sys; from datetime import timedelta; from pathlib import Path; "
        "sys.path.insert(0,'/app/backend'); "
        "os.environ.__setitem__('WEBUI_SECRET_KEY',Path('/app/backend/.webui_secret_key').read_text().strip()) "
        "if not os.environ.get('WEBUI_SECRET_KEY') else None; "
        "from open_webui.models.users import Users; from open_webui.utils.auth import create_token; "
        "u=asyncio.run(Users.get_super_admin_user()); "
        "print(create_token({'id':u.id},expires_delta=timedelta(minutes=5)))"
    )
    result = subprocess.run(
        ["docker.exe", "exec", "josie-open-webui-1", "python", "-c", script],
        check=False, capture_output=True, text=True, timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    token = lines[-1] if result.returncode == 0 and lines else ""
    if len(token) < 20:
        raise RuntimeError("local_openwebui_auth_unavailable")
    return token


def _post_json(url: str, token: str, body: dict[str, Any], *, timeout: int) -> tuple[str, str]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.headers.get_content_type(), response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("local_openwebui_request_failed") from exc


def _completion_text(content_type: str, raw: str) -> str:
    if content_type == "application/json":
        payload = json.loads(raw)
        choices = payload.get("choices") if isinstance(payload, dict) else None
        message = (choices[0].get("message") if choices else None) or {}
        return str(message.get("content") or "")
    chunks: list[str] = []
    for line in raw.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        payload = json.loads(line[6:])
        choices = payload.get("choices") or []
        if choices:
            chunks.append(str((choices[0].get("delta") or {}).get("content") or ""))
        elif isinstance(payload.get("content"), str):
            chunks.append(payload["content"])
    return "".join(chunks)


def verify_josie_http(config: dict[str, Any]) -> bool:
    token = _openwebui_owner_token()
    request = urllib.request.Request(
        config["base_url"] + "/api/models",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("local_openwebui_models_unavailable") from exc
    finally:
        token = ""
    return any(item.get("id") == config["model"] for item in payload.get("data", []))


def deliver_josie_http(action: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    base = {
        "action_id": action["action_id"], "tab_id": None,
        "page_url": config["base_url"] + config["completion_path"],
        "page_title": "Josie local HTTP",
    }
    token = ""
    try:
        token = _openwebui_owner_token()
        scope_id, user_id, assistant_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        content_type, raw = _post_json(
            config["base_url"] + config["completion_path"], token,
            {
                "model": config["model"], "chat_id": scope_id,
                "id": assistant_id, "parent_id": user_id,
                "messages": [{"role": "user", "content": action["payload"]}],
                "stream": False, "tool_ids": config["tool_ids"],
                "filter_ids": config["filter_ids"],
            }, timeout=config["timeout_seconds"],
        )
        raw_text = _completion_text(content_type, raw)
        _, completed_raw = _post_json(
            config["base_url"] + config["completed_path"], token,
            {
                "model": config["model"], "chat_id": scope_id,
                "id": assistant_id, "parent_id": user_id,
                "session_id": f"summit-relay-{scope_id}",
                "filter_ids": config["filter_ids"],
                "messages": [
                    {"id": user_id, "role": "user", "content": action["payload"]},
                    {"id": assistant_id, "parentId": user_id, "role": "assistant",
                     "content": raw_text, "model": config["model"]},
                ],
            }, timeout=config["timeout_seconds"],
        )
        completed = json.loads(completed_raw)
        messages = completed.get("messages") or []
        final_text = str(messages[-1].get("content") or "").strip() if messages else ""
        if not final_text:
            raise RuntimeError("local_openwebui_empty_response")
        return {**base, "ok": True, "assistant_text": final_text,
                "error_code": "", "error_detail": ""}
    except Exception as exc:
        return {**base, "ok": False, "assistant_text": "",
                "error_code": str(exc).splitlines()[0][:80],
                "error_detail": type(exc).__name__}
    finally:
        token = ""


def run_direct(*, project_root: Path, acceptance: bool) -> dict[str, Any]:
    browser_config = load_browser_config(project_root)
    relay_config = load_relay_config(project_root)
    receipts = ReceiptLog(project_root / "data" / "summit-relay" / "receipts.jsonl")
    josie_http_ready = verify_josie_http(browser_config["josie_http"])
    with DirectSummitBrowser(project_root=project_root, config=browser_config) as browser:
        auth = browser.authentication()
        receipts.append({
            "event": "direct_browser_preflight", "transport": "direct_playwright",
            "headless": browser_config["headless"],
            "authentication": {worker: state["authenticated"] for worker, state in auth.items()},
            "josie_http_ready": josie_http_ready,
            "extension_involved": False,
        })
        if not josie_http_ready:
            return {"status": "blocked", "reason": "josie_http_unavailable", "authentication": auth}
        if not all(state["authenticated"] for state in auth.values()):
            labels = {"sophie": "CHATGPT", "bernie": "GEMINI"}
            missing = [labels[worker] for worker, state in auth.items() if not state["authenticated"]]
            reason = "; ".join(f"AUTH_REQUIRED: {label}" for label in missing)
            return {"status": "blocked", "reason": reason, "authentication": auth}
        if not acceptance:
            return {"status": "ready", "authentication": auth, "messages_sent": 0}
        relay = AcceptanceRelay(relay_config, receipts)
        for _ in range(4):
            action = relay.next_action()
            if action is None:
                break
            result = (
                deliver_josie_http(action, browser_config["josie_http"])
                if action["worker"] == "josie"
                else browser.send_and_capture(action)
            )
            report = relay.submit_result(result)
            if report["status"] != "running":
                return {**report, "transport": "direct_playwright"}
        return {**relay.status_report(), "transport": "direct_playwright"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Direct Playwright transport for Summit Relay v0.1")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--initialize-profile", action="store_true")
    parser.add_argument("--acceptance", action="store_true")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    if args.initialize_profile:
        path = initialize_profile(project_root=root)
        print(json.dumps({"status": "initialized", "profile": str(path)}))
        return 0
    result = run_direct(project_root=root, acceptance=args.acceptance)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"ready", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

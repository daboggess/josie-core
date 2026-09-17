from __future__ import annotations

import fnmatch
import json
import os
import re
from collections.abc import Callable
from pathlib import Path


CAPABILITIES = {
    "package_installs",
    "software_installs",
    "model_pulls",
    "network_side_effects",
    "host_environment_mutation",
}


def supervised_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    return env

COMMAND_RULES = {
    "package_installs": [
        "*pip install*", "*pip * install*", "*python -m pip install*", "*python.exe -m pip install*",
        "*pipx install*", "*conda install*", "*uv add*", "*uv pip install*", "*poetry add*",
        "*npm install*", "*npm add*", "*pnpm add*", "*yarn add*",
    ],
    "software_installs": ["*winget install*", "*choco install*", "*scoop install*"],
    "model_pulls": ["*ollama pull*", "*huggingface-cli download*", "*hf download*"],
    "network_side_effects": ["curl *", "wget *", "git clone*", "git pull*", "*Invoke-WebRequest*", "*Invoke-RestMethod*"],
    "host_environment_mutation": [
        "setx *", "reg add*", "*schtasks *", "*sc create*", "*sc stop*",
        "*net stop*", "*start-service*", "*stop-service*", "*restart-service*",
        "*git reset --hard*", "*git clean *", "*git branch -d *",
        "rm *", "* rm *", "del *", "* del *", "*remove-item*",
        "taskkill *", "*taskkill *", "*stop-process*",
    ],
}


def requested_capabilities(raw: dict) -> set[str]:
    return set(raw.get("side_effect_capabilities", []))


def classify_command(command: str) -> str | None:
    normalized = re.sub(r"\s+", " ", command.strip()).lower()
    for capability, patterns in COMMAND_RULES.items():
        if any(fnmatch.fnmatchcase(normalized, pattern.lower()) for pattern in patterns):
            return capability
    return None


def authorize_command(command: str, allowed: set[str]) -> dict:
    capability = classify_command(command)
    permitted = capability is None or capability in allowed
    return {
        "command": command,
        "capability": capability,
        "allowed": permitted,
        "reason": "ALLOWED" if permitted else f"DENIED_{capability.upper()}",
        "prevented_before_execution": not permitted,
    }


def execute_if_authorized(command: str, allowed: set[str], executor: Callable[[], object]) -> tuple[dict, object | None]:
    decision = authorize_command(command, allowed)
    return (decision, executor() if decision["allowed"] else None)


def bash_permission_rules(allowed: set[str]) -> dict[str, str]:
    rules = {"*": "allow"}
    for capability, patterns in COMMAND_RULES.items():
        if capability not in allowed:
            for pattern in patterns:
                rules[pattern] = "deny"
    return rules


def policy_summary(raw: dict) -> dict:
    requested = sorted(requested_capabilities(raw))
    return {
        "requested_capabilities": requested,
        "allowed_capabilities": requested,
        "default_denied_capabilities": sorted(CAPABILITIES - set(requested)),
        "denied_actions": [],
    }


def load_markdown_agent(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError("agent profile lacks YAML frontmatter")
    header, body = text[4:].split("\n---\n", 1)
    values: dict[str, object] = {}
    current_section = None
    section_dict: dict[str, str] = {}
    for line in header.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        if line.startswith("  ") and current_section:
            if ":" in trimmed:
                sub_k, sub_v = trimmed.split(":", 1)
                section_dict[sub_k.strip().strip('"').strip("'")] = sub_v.strip().strip('"').strip("'")
            continue
        if ":" not in line:
            continue
        current_section = None
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "permission":
            current_section = "permission"
            section_dict = {}
            values["permission"] = section_dict
            continue
        if key in {"description", "mode", "model"}:
            values[key] = value
        elif key == "temperature":
            values[key] = float(value)
        elif key == "steps":
            values[key] = int(value)
    values["prompt"] = body.strip()
    return values


def secure_agent(config: dict, agent_id: str, allowed: set[str], profile_path: Path | None = None) -> None:
    agents = config.setdefault("agent", {})
    if profile_path is not None:
        if profile_path.stem != agent_id:
            raise ValueError("agent profile filename does not match requested agent ID")
        agents[agent_id] = load_markdown_agent(profile_path)
    if agent_id not in agents or not isinstance(agents[agent_id], dict):
        raise ValueError(f"agent is not defined: {agent_id}")
    raw_perms = agents[agent_id].get("permission")
    if isinstance(raw_perms, dict) and raw_perms:
        first_key = next(iter(raw_perms.keys()))
        if first_key != "*":
            raise ValueError(
                f"Agent profile '{agent_id}' must declare '*' as the first permission rule to preserve OpenCode rule precedence; found '{first_key}'"
            )
    permissions: dict[str, object] = {
        "*": "deny", "read": "allow", "write": "allow", "edit": "allow",
        "apply_patch": "allow", "glob": "allow", "grep": "allow", "list": "allow",
        "bash": bash_permission_rules(allowed), "todowrite": "allow", "lsp": "allow",
        "task": "deny", "question": "deny",
        "webfetch": "deny", "websearch": "deny", "external_directory": "deny",
    }
    if isinstance(raw_perms, dict):
        for k, v in raw_perms.items():
            if k not in permissions:
                permissions[k] = v
    agents[agent_id]["permission"] = permissions


def denied_events(path: Path, allowed: set[str]) -> list[dict]:
    denied = []
    if not path.is_file():
        return denied
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        part = event.get("part") or {}
        state = part.get("state") or {}
        if event.get("type") != "tool_use" or part.get("tool") != "bash":
            continue
        command = (state.get("input") or {}).get("command", "")
        decision = authorize_command(command, allowed)
        if not decision["allowed"]:
            decision["tool_status"] = state.get("status")
            decision["prevented_before_execution"] = state.get("status") != "completed"
            denied.append(decision)
    return denied

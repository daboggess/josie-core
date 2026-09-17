from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

from .authority import requested_capabilities, secure_agent, supervised_environment
from .process_control import run_contained
from .prompt_compiler import compile_prompt
from .work_order import WorkOrder


DEFAULT_OPENCODE = Path(r"I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe")
DEFAULT_GOOSE = Path(r"I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe")
DEFAULT_AIDER = Path(r"I:\Josie-Storage\apps\aider-env\Scripts\aider.exe")


def executable_version(executable: Path) -> str:
    result = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=10)
    return result.stdout.strip() or result.stderr.strip()


def build_argv(order: WorkOrder, retry: bool = False, stdout_path: Path | None = None) -> tuple[list[str], str]:
    harness = order.raw["harness"]
    if harness == "goose":
        executable = Path(order.raw.get("harness_executable", DEFAULT_GOOSE)).resolve()
        if not executable.is_file():
            raise FileNotFoundError(str(executable))
        prompt = compile_prompt(order, retry=retry)
        argv = [
            str(executable), "run", "--no-session", "--no-profile",
            "--with-builtin", "developer", "--provider", "ollama",
            "--model", order.raw["model"], "--max-tool-repetitions",
            str(order.raw.get("max_tool_repetitions", 3)), "--max-turns", "12",
            "--output-format", "stream-json", "--text", prompt,
        ]
        return argv, executable_version(executable)
    if harness == "opencode":
        executable = Path(order.raw.get("harness_executable", DEFAULT_OPENCODE)).resolve()
        if not executable.is_file():
            raise FileNotFoundError(str(executable))
        prompt = compile_prompt(order, retry=retry)
        argv = [str(executable), "run", "--pure", "--auto", "--format", "json", "--model", order.raw["model"], "--dir", str(order.workspace)]
        if order.raw.get("agent"):
            argv += ["--agent", order.raw["agent"]]
        return argv + [prompt], executable_version(executable)
    if harness == "aider":
        executable = Path(order.raw.get("harness_executable", DEFAULT_AIDER)).resolve()
        if not executable.is_file():
            raise FileNotFoundError(str(executable))
        prompt = compile_prompt(order, retry=retry)
        edit_format = order.raw.get("edit_format", "diff")
        target_files = [str(order.workspace / p) for p in order.allowed_changed_paths]
        argv = [
            str(executable),
            "--model", order.raw["model"],
            "--edit-format", edit_format,
            "--yes-always",
            "--no-git",
            "--no-auto-commits",
            "--no-analytics",
            "--no-check-update",
            "--no-auto-lint",
            "--encoding", "utf-8",
            "--message", prompt,
        ]
        if stdout_path is not None:
            argv += [
                "--chat-history-file", str(stdout_path.with_suffix(".aider.chat.history.md")),
                "--input-history-file", str(stdout_path.with_suffix(".aider.input.history")),
            ]
        for ro in order.raw.get("read_only_paths", []):
            argv += ["--read", str(order.workspace / ro)]
        argv += target_files
        return argv, executable_version(executable)
    if harness == "mock":
        executable = Path(order.raw["harness_executable"]).resolve()
        if not executable.is_file():
            raise FileNotFoundError(str(executable))
        return [str(executable), str(Path(__file__).parent / "tests" / "mock_worker.py"), order.raw["objective"]], "mock"
    raise ValueError(f"unsupported harness: {harness}")


def launch(order: WorkOrder, stdout_path: Path, stderr_path: Path, retry: bool = False) -> dict:
    argv, version = build_argv(order, retry=retry, stdout_path=stdout_path)
    env = supervised_environment()
    if order.raw["harness"] in {"goose", "opencode", "aider"}:
        for key in list(env):
            if key.upper().startswith((
                    "OPENAI_", "ANTHROPIC_", "GEMINI_", "GOOGLE_API_",
                    "AZURE_", "AWS_", "DATABRICKS_")):
                env.pop(key)
    if order.raw["harness"] == "goose":
        env.update(
            GOOSE_PROVIDER="ollama",
            GOOSE_MODEL=order.raw["model"],
            OLLAMA_HOST=order.raw.get("ollama_url", "http://127.0.0.1:11434"),
            GOOSE_INPUT_LIMIT=str(order.raw.get("context_limit", 8192)),
            GOOSE_MAX_TOKENS="2048",
            GOOSE_MODE="auto",
            GOOSE_MAX_TURNS="12",
        )
    if order.raw["harness"] == "opencode":
        if order.raw.get("harness_config"):
            config = json.loads(Path(order.raw["harness_config"]).read_text(encoding="utf-8"))
            if order.raw.get("agent"):
                profile = Path(order.raw["agent_profile"]).resolve() if order.raw.get("agent_profile") else None
                secure_agent(config, order.raw["agent"], requested_capabilities(order.raw), profile)
            env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
        env.update(OPENCODE_DISABLE_AUTOUPDATE="true", OPENCODE_DISABLE_MODELS_FETCH="true", OPENCODE_DISABLE_DEFAULT_PLUGINS="true", OPENCODE_DISABLE_LSP_DOWNLOAD="true", OPENCODE_DISABLE_CLAUDE_CODE="true", OPENCODE_GIT_BASH_PATH="C:/Program Files/Git/bin/bash.exe")
    if order.raw["harness"] == "aider":
        env.update(
            OLLAMA_API_BASE=order.raw.get("ollama_url", "http://127.0.0.1:11434"),
            AIDER_ANALYTICS="false",
            AIDER_NO_CHECK_UPDATE="true",
            AIDER_AUTO_LINT="false",
            AIDER_ENCODING="utf-8",
            PYTHONIOENCODING="utf-8",
            PYTHONUTF8="1",
            AIDER_CHAT_HISTORY_FILE=str(stdout_path.with_suffix(".aider.chat.history.md")),
            AIDER_INPUT_HISTORY_FILE=str(stdout_path.with_suffix(".aider.input.history")),
        )
    activity_probe = None
    meaningful_activity_probe = None
    environment_evidence = {}
    if order.raw["harness"] in {"goose", "opencode", "aider"}:
        base_url = order.raw.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
        def activity_probe() -> dict:
            with urllib.request.urlopen(base_url + "/api/ps", timeout=0.5) as response:
                payload = json.load(response)
            return {"ollama_loaded_models": sorted(
                item.get("name") or item.get("model") for item in payload.get("models", [])
                if item.get("name") or item.get("model"))}
        def meaningful_activity_probe() -> bool:
            if not stdout_path.is_file():
                return False
            with stdout_path.open("rb") as handle:
                size = stdout_path.stat().st_size
                handle.seek(max(0, size - 1024 * 1024))
                output = handle.read()
            if order.raw["harness"] == "goose":
                markers = (b'"type":"toolRequest"', b'"type": "toolRequest"')
            elif order.raw["harness"] == "aider":
                markers = (b"Applied edit to", b"Applied edit", b"Tokens:", b"diff --git", b"```", b"model", b"aider")
            else:
                markers = (b'"type":"tool_use"', b'"type": "tool_use"')
            return any(marker in output for marker in markers)
        environment_evidence = {
            "provider_credentials_removed": [
                "OPENAI_*", "ANTHROPIC_*", "GEMINI_*", "GOOGLE_API_*",
                "AZURE_*", "AWS_*", "DATABRICKS_*",
            ],
            "provider": "ollama",
            "model": order.raw["model"],
            "context_limit": order.raw.get("context_limit", 8192),
        }
        if order.raw["harness"] == "opencode":
            environment_evidence.update({
            "overrides": {key: env[key] for key in (
                "PYTHONDONTWRITEBYTECODE", "PYTEST_ADDOPTS", "OPENCODE_DISABLE_AUTOUPDATE",
                "OPENCODE_DISABLE_MODELS_FETCH", "OPENCODE_DISABLE_DEFAULT_PLUGINS",
                "OPENCODE_DISABLE_LSP_DOWNLOAD", "OPENCODE_DISABLE_CLAUDE_CODE",
                "OPENCODE_GIT_BASH_PATH")},
            "config_source": "OPENCODE_CONFIG_CONTENT",
            })
        elif order.raw["harness"] == "aider":
            environment_evidence.update({
                "overrides": {key: env[key] for key in (
                    "PYTHONDONTWRITEBYTECODE", "PYTEST_ADDOPTS", "OLLAMA_API_BASE",
                    "AIDER_ANALYTICS", "AIDER_NO_CHECK_UPDATE") if key in env},
                "config_source": None,
            })
        else:
            environment_evidence.update({
                "overrides": {key: env[key] for key in (
                    "PYTHONDONTWRITEBYTECODE", "PYTEST_ADDOPTS", "GOOSE_PROVIDER",
                    "GOOSE_MODEL", "GOOSE_INPUT_LIMIT", "GOOSE_MAX_TOKENS",
                    "GOOSE_MODE", "GOOSE_MAX_TURNS")},
                "config_source": order.raw.get("goose_config"),
                "extensions": ["builtin:developer"],
            })
    result = run_contained(
        argv, str(order.workspace), order.raw["timeout_seconds"], str(stdout_path),
        str(stderr_path), env=env, activity_probe=activity_probe,
        meaningful_activity_probe=meaningful_activity_probe,
        stall_timeout=order.raw.get("stall_seconds"),
    )
    return {"argv": argv, "version": version, "pid": result.pid,
            "exit_code": result.exit_code, "timed_out": result.timed_out,
            "stalled": result.stalled, "elapsed_seconds": result.elapsed_seconds,
            "cleanup": result.cleanup, "liveness": result.liveness,
            "environment_evidence": environment_evidence}

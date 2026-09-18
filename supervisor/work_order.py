from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .prompt_contract import DEFAULT_PROMPT_CONTRACT_VERSION, SUPPORTED_PROMPT_CONTRACT_VERSIONS


class ValidationError(ValueError):
    pass


KNOWN_FIELDS = {
    "schema_version", "job_id", "objective", "workspace", "harness", "model",
    "allowed_changed_paths", "forbidden_paths", "timeout_seconds", "max_attempts",
    "acceptance", "prompt_profile", "receipt_destination", "harness_executable",
    "first_action", "strict_validation", "ollama_url", "harness_config", "agent",
    "agent_profile", "side_effect_capabilities", "requires_modification",
    "role", "current_state", "environment", "retrieved_evidence", "retrieval_summary",
    "prohibited_actions", "fallback_conditions", "stall_seconds",
    "primary_harness_executable", "fallback_harness_executable",
    "goose_config", "context_limit", "max_tool_repetitions",
    "reporting_instructions", "edit_format", "aider_config", "read_only_paths",
    "prompt_contract_version", "worker_failure_modes", "resource_rules", "receipt_instructions",
}
KNOWN_ACCEPTANCE = {"file_exists", "file_exact", "command", "changed_paths", "no_unexpected_files"}


def _relative_rule(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("path rule must be a nonempty string")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or ":" in normalized:
        raise ValidationError(f"unsafe path rule: {value}")
    return path.as_posix().lstrip("./")


@dataclass(frozen=True)
class WorkOrder:
    raw: dict[str, Any]
    workspace: Path
    allowed_changed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]

    @property
    def prompt_contract_version(self) -> str:
        return self.raw.get("prompt_contract_version", DEFAULT_PROMPT_CONTRACT_VERSION)

    @classmethod
    def load(cls, path: Path) -> "WorkOrder":
        return cls.validate(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def validate(cls, data: Any) -> "WorkOrder":
        if not isinstance(data, dict):
            raise ValidationError("work order must be a JSON object")
        required = {
            "schema_version", "job_id", "objective", "workspace", "harness", "model",
            "allowed_changed_paths", "timeout_seconds", "max_attempts", "acceptance",
            "prompt_profile", "receipt_destination",
        }
        missing = sorted(required - data.keys())
        if missing:
            raise ValidationError(f"missing fields: {', '.join(missing)}")
        if data.get("strict_validation", True):
            unknown = sorted(data.keys() - KNOWN_FIELDS)
            if unknown:
                raise ValidationError(f"unknown fields: {', '.join(unknown)}")
        for key in ("schema_version", "job_id", "objective", "harness", "model", "prompt_profile"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise ValidationError(f"{key} must be a nonempty string")
        if data["harness"] not in {"coder", "goose", "opencode", "mock", "aider"}:
            raise ValidationError("unsupported harness")
        workspace = Path(data["workspace"]).resolve()
        if not workspace.is_absolute() or not workspace.is_dir():
            raise ValidationError("workspace must be an existing absolute directory")
        if not isinstance(data["timeout_seconds"], (int, float)) or data["timeout_seconds"] <= 0:
            raise ValidationError("timeout_seconds must be positive")
        if not isinstance(data["max_attempts"], int) or data["max_attempts"] <= 0:
            raise ValidationError("max_attempts must be a positive integer")
        allowed = data["allowed_changed_paths"]
        if not isinstance(allowed, list) or not allowed:
            raise ValidationError("allowed_changed_paths must be nonempty")
        allowed_rules = tuple(_relative_rule(item) for item in allowed)
        forbidden = tuple(_relative_rule(item) for item in data.get("forbidden_paths", []))
        acceptance = data["acceptance"]
        if not isinstance(acceptance, list) or not acceptance:
            raise ValidationError("acceptance checks are required")
        for check in acceptance:
            if not isinstance(check, dict) or check.get("type") not in KNOWN_ACCEPTANCE:
                raise ValidationError("unknown acceptance primitive")
            if "path" in check:
                _relative_rule(check["path"])
            if check["type"] == "command":
                if not isinstance(check.get("argv"), list) or not check["argv"]:
                    raise ValidationError("command acceptance requires argv")
                if not all(isinstance(arg, str) and arg for arg in check["argv"]):
                    raise ValidationError("command acceptance argv must contain nonempty strings")
        receipt = Path(data["receipt_destination"]).resolve()
        if not receipt.is_absolute():
            raise ValidationError("receipt_destination must be absolute")
        if "harness_config" in data and not Path(data["harness_config"]).resolve().is_file():
            raise ValidationError("harness_config must be an existing file")
        if "agent_profile" in data and not Path(data["agent_profile"]).resolve().is_file():
            raise ValidationError("agent_profile must be an existing file")
        capabilities = data.get("side_effect_capabilities", [])
        if not isinstance(capabilities, list) or any(item not in {
            "package_installs", "software_installs", "model_pulls",
            "network_side_effects", "host_environment_mutation",
        } for item in capabilities):
            raise ValidationError("unknown side-effect capability")
        if not isinstance(data.get("requires_modification", False), bool):
            raise ValidationError("requires_modification must be boolean")
        if "stall_seconds" in data and (
                not isinstance(data["stall_seconds"], (int, float))
                or data["stall_seconds"] <= 0
                or data["stall_seconds"] > data["timeout_seconds"]):
            raise ValidationError("stall_seconds must be positive and no greater than timeout_seconds")
        if "context_limit" in data and (
                not isinstance(data["context_limit"], int)
                or not 2048 <= data["context_limit"] <= 32768):
            raise ValidationError("context_limit must be between 2048 and 32768")
        if "max_tool_repetitions" in data and (
                not isinstance(data["max_tool_repetitions"], int)
                or not 1 <= data["max_tool_repetitions"] <= 10):
            raise ValidationError("max_tool_repetitions must be between 1 and 10")
        if not isinstance(data.get("retrieved_evidence", []), list):
            raise ValidationError("retrieved_evidence must be a list")
        if not isinstance(data.get("retrieval_summary", {}), dict):
            raise ValidationError("retrieval_summary must be an object")
        if "prompt_contract_version" in data:
            pcv = data["prompt_contract_version"]
            if not isinstance(pcv, str) or not pcv.strip():
                raise ValidationError("prompt_contract_version must be a nonempty string")
            if pcv not in SUPPORTED_PROMPT_CONTRACT_VERSIONS:
                raise ValidationError(f"unsupported prompt_contract_version: {pcv}")
        else:
            data.setdefault("prompt_contract_version", DEFAULT_PROMPT_CONTRACT_VERSION)
        if "worker_failure_modes" in data:
            wfm = data["worker_failure_modes"]
            if not isinstance(wfm, list) or not all(isinstance(item, str) and item.strip() for item in wfm):
                raise ValidationError("worker_failure_modes must be a list of nonempty strings")
        if "resource_rules" in data:
            rr = data["resource_rules"]
            if isinstance(rr, list):
                if not all(isinstance(item, str) and item.strip() for item in rr):
                    raise ValidationError("resource_rules must be a string or list of nonempty strings")
            elif not isinstance(rr, str) or not rr.strip():
                raise ValidationError("resource_rules must be a string or list of nonempty strings")
        if "receipt_instructions" in data:
            ri = data["receipt_instructions"]
            if not isinstance(ri, str) or not ri.strip():
                raise ValidationError("receipt_instructions must be a nonempty string")
        return cls(data, workspace, allowed_rules, forbidden)

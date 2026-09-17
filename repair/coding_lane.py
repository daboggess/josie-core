from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .models import RepairReceipt, RepairTicket


UNLOAD_ACTION = "unload_loaded_coder_model"
SUPPORTED_FAILURE_REASONS = {"FAIL_TIMEOUT", "PREMATURE_STOP"}


def _http_json(url: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


class CodingLaneRepair:
    """One narrow playbook: reset a resident coder model, then ask Supervisor to prove service."""

    def __init__(
        self,
        http_json: Callable[..., dict[str, Any]] = _http_json,
        run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.http_json = http_json
        self.run = run

    def observe(self, ticket: RepairTicket) -> dict[str, Any]:
        expected = ticket.expected_state
        executable = Path(expected["opencode_executable"])
        version = self.run(
            [str(executable), "--version"], capture_output=True, text=True, timeout=10,
        )
        ollama_url = expected.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
        tags = self.http_json(ollama_url + "/api/tags")
        loaded = self.http_json(ollama_url + "/api/ps")
        evidence = [self._receipt_summary(Path(ref)) for ref in ticket.receipt_refs]
        return {
            "opencode_exists": executable.is_file(),
            "opencode_version": (version.stdout or version.stderr).strip(),
            "ollama_version": self.http_json(ollama_url + "/api/version").get("version"),
            "models": sorted(item.get("name") or item.get("model") for item in tags.get("models", [])),
            "loaded_models": sorted(item.get("name") or item.get("model") for item in loaded.get("models", [])),
            "failure_receipts": evidence,
        }

    @staticmethod
    def _receipt_summary(path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "ref": str(path),
            "final_status": data.get("final_status"),
            "reason": data.get("reason"),
            "model": data.get("requested_model"),
            "harness_executable": data.get("harness_executable"),
            "files_changed": data.get("worker_changed_paths") or data.get("changed_files") or [],
            "tool_activity": data.get("tool_activity") or [],
        }

    @staticmethod
    def compare(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
        differences: list[str] = []
        if actual["opencode_version"] != expected["opencode_version"]:
            differences.append("opencode_version")
        if expected["model"].split("/", 1)[-1] not in actual["models"]:
            differences.append("required_model_missing")
        if expected["model"].split("/", 1)[-1] in actual["loaded_models"]:
            differences.append("failed_attempt_model_still_loaded")
        return differences

    @staticmethod
    def _shared_lane_evidenced(actual: dict[str, Any]) -> bool:
        receipts = actual["failure_receipts"]
        models = {item["model"] for item in receipts if item["model"]}
        harnesses = {item["harness_executable"] for item in receipts if item["harness_executable"]}
        qualifying = [
            item for item in receipts
            if item["final_status"] == "FAIL"
            and item["reason"] in SUPPORTED_FAILURE_REASONS
            and not item["files_changed"]
            and not item["tool_activity"]
        ]
        return len(qualifying) >= 2 and len(models) >= 2 and len(harnesses) == 1

    def repair(self, ticket: RepairTicket) -> RepairReceipt:
        result = RepairReceipt(
            repair_id=ticket.repair_id,
            failed_job_id=ticket.failed_job_id,
            expected_state=ticket.expected_state,
        )
        try:
            before = self.observe(ticket)
            result.actual_before = before
            result.material_differences = self.compare(ticket.expected_state, before)
            model = ticket.expected_state["model"].split("/", 1)[-1]
            if "failed_attempt_model_still_loaded" in result.material_differences:
                if UNLOAD_ACTION not in ticket.authorized_recovery_actions:
                    result.reason = "RECOVERY_NOT_AUTHORIZED"
                    return result
                if not self._shared_lane_evidenced(before):
                    result.reason = "INSUFFICIENT_SHARED_LANE_EVIDENCE"
                    return result
                ollama_url = ticket.expected_state.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
                self.http_json(ollama_url + "/api/generate", body={"model": model, "keep_alive": 0})
                result.recovery_actions.append({"action": UNLOAD_ACTION, "model": model})
            result.actual_after = self.observe(ticket)
            result.attempts_used = 1
            receipt_ref = self._run_supervised_probe(ticket)
            authoritative = json.loads(Path(receipt_ref).read_text(encoding="utf-8"))
            result.supervisor_receipt_ref = receipt_ref
            result.externally_verified = authoritative.get("final_status") == "PASS"
            result.final_status = "PASS" if result.externally_verified else "FAIL"
            result.reason = authoritative.get("reason", "INVALID_SUPERVISOR_RECEIPT")
            return result
        except Exception as exc:
            result.final_status = "FAIL"
            result.reason = f"{type(exc).__name__}: {exc}"
            return result

    def _run_supervised_probe(self, ticket: RepairTicket) -> str:
        expected = ticket.expected_state
        order = {
            "schema_version": "1",
            "job_id": f"{ticket.repair_id}-probe",
            "objective": expected["probe_objective"],
            "first_action": expected["probe_first_action"],
            "workspace": expected["probe_workspace"],
            "harness": "opencode",
            "harness_executable": expected["opencode_executable"],
            "harness_config": expected["opencode_config"],
            "agent": "josie-coder",
            "agent_profile": expected["agent_profile"],
            "model": expected["model"],
            "side_effect_capabilities": [],
            "requires_modification": True,
            "allowed_changed_paths": expected["allowed_changed_paths"],
            "timeout_seconds": expected.get("timeout_seconds", 120),
            "max_attempts": 1,
            "acceptance": list(ticket.acceptance),
            "prompt_profile": "josie-coder-v1",
            "receipt_destination": expected["supervisor_receipt_destination"],
            "ollama_url": expected.get("ollama_url", "http://127.0.0.1:11434"),
        }
        with tempfile.TemporaryDirectory(prefix="josie-repair-") as directory:
            order_path = Path(directory) / "work-order.json"
            order_path.write_text(json.dumps(order), encoding="utf-8")
            completed = self.run(
                [expected["python_executable"], "-m", "supervisor.run_job", str(order_path)],
                cwd=expected["josie_root"], capture_output=True, text=True,
                timeout=expected.get("supervisor_timeout_seconds", 180),
            )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Supervisor failed")
        output = json.loads(completed.stdout.strip().splitlines()[-1])
        return output["receipt"]

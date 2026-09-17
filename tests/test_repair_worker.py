from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from repair.coding_lane import CodingLaneRepair, UNLOAD_ACTION
from repair.models import InvalidRepairTicket, RepairTicket


class RepairWorkerTests(unittest.TestCase):
    def ticket(self, **updates):
        value = {
            "repair_id": "repair-1",
            "department": "coding",
            "failed_job_id": "job-1",
            "receipt_refs": ["qwen.json", "gemma.json"],
            "expected_state": {"opencode_version": "1.18.23", "model": "ollama/qwen3:14b"},
            "observed_failure_class": "coding_worker_unresponsive",
            "authorized_recovery_actions": [UNLOAD_ACTION],
            "acceptance": [{"type": "file_exact", "path": "probe.txt", "content": "OK"}],
            "attempt_budget": 1,
        }
        value.update(updates)
        return RepairTicket.from_dict(value)

    def test_rejects_non_coding_playbook(self):
        with self.assertRaises(InvalidRepairTicket):
            self.ticket(observed_failure_class="anything_else")

    def test_compare_identifies_only_material_lane_differences(self):
        actual = {
            "opencode_version": "1.18.23", "models": ["qwen3:14b"],
            "loaded_models": ["qwen3:14b"],
        }
        self.assertEqual(
            CodingLaneRepair.compare(self.ticket().expected_state, actual),
            ["failed_attempt_model_still_loaded"],
        )

    def test_shared_lane_requires_distinct_models_and_no_activity(self):
        actual = {"failure_receipts": [
            {"final_status": "FAIL", "reason": "FAIL_TIMEOUT", "model": "ollama/qwen3:14b",
             "harness_executable": "opencode.exe", "files_changed": [], "tool_activity": []},
            {"final_status": "FAIL", "reason": "FAIL_TIMEOUT", "model": "ollama/gemma4:12b",
             "harness_executable": "opencode.exe", "files_changed": [], "tool_activity": []},
        ]}
        self.assertTrue(CodingLaneRepair._shared_lane_evidenced(actual))
        actual["failure_receipts"][1]["tool_activity"] = [{"tool": "edit"}]
        self.assertFalse(CodingLaneRepair._shared_lane_evidenced(actual))

    def test_receipt_summary_keeps_recovery_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(json.dumps({
                "final_status": "FAIL", "reason": "PREMATURE_STOP",
                "requested_model": "ollama/qwen3:14b", "harness_executable": "opencode.exe",
                "worker_changed_paths": [], "tool_activity": [],
            }), encoding="utf-8")
            summary = CodingLaneRepair._receipt_summary(path)
        self.assertEqual(summary["reason"], "PREMATURE_STOP")
        self.assertEqual(summary["files_changed"], [])

    def test_only_supervisor_pass_can_declare_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = Path(directory) / "supervisor.json"
            receipt_path.write_text(
                json.dumps({"final_status": "FAIL", "reason": "FAIL_ACCEPTANCE"}),
                encoding="utf-8",
            )

            class ControlledRepair(CodingLaneRepair):
                def observe(self, ticket):
                    return {
                        "opencode_version": "1.18.23", "models": ["qwen3:14b"],
                        "loaded_models": [], "failure_receipts": [],
                    }

                def _run_supervised_probe(self, ticket):
                    return str(receipt_path)

            result = ControlledRepair().repair(self.ticket())

        self.assertEqual(result.final_status, "FAIL")
        self.assertFalse(result.externally_verified)
        self.assertEqual(result.attempts_used, 1)


if __name__ == "__main__":
    unittest.main()

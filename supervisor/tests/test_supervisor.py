from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.policy import decide, model_race_verdict
from supervisor.process_control import pid_exists
from supervisor.receipts import write_receipt
from supervisor.run_job import execute
from supervisor.work_order import ValidationError, WorkOrder


class SupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(__file__).parent / ".tmp" / uuid.uuid4().hex
        cls.base.mkdir(parents=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(Path(__file__).parent / ".tmp", ignore_errors=True)

    def setUp(self):
        self.workspace = self.base / uuid.uuid4().hex
        self.workspace.mkdir()
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        self.receipts = self.base / "receipts" / self.workspace.name

    def order(self, objective="allowed", acceptance=None, allowed=None, timeout=5):
        return {"schema_version": "1", "job_id": uuid.uuid4().hex, "objective": objective, "workspace": str(self.workspace), "harness": "mock", "harness_executable": sys.executable, "model": "mock/exact", "allowed_changed_paths": allowed or ["allowed.txt"], "timeout_seconds": timeout, "max_attempts": 1, "acceptance": acceptance or [{"type": "file_exact", "path": "allowed.txt", "content": "OK"}], "prompt_profile": "test", "receipt_destination": str(self.receipts)}

    def execute_order(self, data):
        path = self.workspace / "order.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        data["allowed_changed_paths"] = list(data["allowed_changed_paths"]) + ["order.json"]
        path.write_text(json.dumps(data), encoding="utf-8")
        return execute(path)[0]

    def test_01_valid_allowed_acceptance_pass(self):
        self.assertEqual(self.execute_order(self.order())["final_status"], "PASS")

    def test_02_malformed_rejected_before_launch(self):
        invalid_timeout = self.order(); invalid_timeout["timeout_seconds"] = 0
        traversal = self.order(); traversal["allowed_changed_paths"] = ["../escape.txt"]
        for data in (invalid_timeout, traversal):
            with self.assertRaises(ValidationError):
                WorkOrder.validate(data)

    def test_03_nonzero_worker_fails(self):
        receipt = self.execute_order(self.order(objective="nonzero"))
        self.assertEqual(receipt["reason"], "FAIL_WORKER")

    def test_04_timeout_kills_parent_and_child(self):
        pid_file = self.workspace / "child.pid"
        receipt = self.execute_order(self.order(objective=f"timeout:{pid_file}", allowed=["child.pid"], acceptance=[{"type": "file_exists", "path": "child.pid"}], timeout=1))
        self.assertEqual(receipt["reason"], "FAIL_TIMEOUT")
        self.assertTrue(receipt["cleanup"]["gone"])
        child_pid = int(pid_file.read_text())
        for _ in range(20):
            if not pid_exists(child_pid): break
            time.sleep(.1)
        self.assertFalse(pid_exists(child_pid))

    def test_05_expected_authorized_edit_passes(self):
        receipt = self.execute_order(self.order(acceptance=[{"type": "changed_paths"}, {"type": "file_exists", "path": "allowed.txt"}]))
        self.assertEqual(receipt["reason"], "PASS")

    def test_06_unauthorized_edit_fails_scope(self):
        receipt = self.execute_order(self.order(objective="unauthorized"))
        self.assertEqual(receipt["reason"], "FAIL_SCOPE")
        self.assertIn("intruder.txt", receipt["scope_violations"])

    def test_07_acceptance_command_failure(self):
        data = self.order(acceptance=[{"type": "command", "argv": [sys.executable, "-c", "raise SystemExit(3)"], "expected_exit_code": 0}])
        self.assertEqual(self.execute_order(data)["reason"], "FAIL_ACCEPTANCE")

    def test_07b_textual_pass_cannot_override_failed_external_acceptance(self):
        data = self.order(
            objective="STATUS: PASS",
            acceptance=[{"type": "command", "argv": [sys.executable, "-c", "raise SystemExit(3)"], "expected_exit_code": 0}],
        )
        receipt = self.execute_order(data)
        self.assertEqual(receipt["final_status"], "FAIL")
        self.assertEqual(receipt["reason"], "FAIL_ACCEPTANCE")

    def test_07c_textual_pass_with_zero_tool_activity_fails_no_tool_activity(self):
        data = self.order(
            objective="STATUS: PASS",
            acceptance=[{"type": "command", "argv": [sys.executable, "-c", "pass"], "expected_exit_code": 0}],
        )
        data["requires_modification"] = True
        receipt = self.execute_order(data)
        self.assertEqual(receipt["final_status"], "FAIL")
        self.assertEqual(receipt["reason"], "FAIL_NO_TOOL_ACTIVITY")

    def test_08_preexisting_dirty_file_preserved_not_attributed(self):
        dirty = self.workspace / "dirty.txt"; dirty.write_text("KEEP", encoding="utf-8")
        receipt = self.execute_order(self.order())
        self.assertEqual(dirty.read_text(encoding="utf-8"), "KEEP")
        self.assertNotIn("dirty.txt", receipt["changed_files"])

    def test_09_not_run_cannot_pass_or_win(self):
        self.assertEqual(decide(launched=False, preflight_ok=True, timed_out=False, exit_code=0, violations=[], acceptance=[{"passed": True}]), ("FAIL", "NOT_RUN"))
        with self.assertRaises(ValueError): model_race_verdict([{"name": "x", "status": "NOT_RUN", "declared_winner": True}], "BASELINE")

    def test_10_blocked_cannot_pass_or_win(self):
        self.assertEqual(decide(launched=False, preflight_ok=False, timed_out=False, exit_code=None, violations=[], acceptance=[])[0], "BLOCKED")
        with self.assertRaises(ValueError): model_race_verdict([{"name": "x", "status": "BLOCKED", "declared_winner": True}], "BASELINE")

    def test_11_contradictory_winners_rejected(self):
        rows = [{"name": x, "status": "PASS", "required_evidence": True, "beats_baseline": True} for x in ("a", "b")]
        with self.assertRaises(ValueError): model_race_verdict(rows, "BASELINE")

    def test_12_receipt_cannot_be_overwritten(self):
        first = write_receipt(self.receipts, {"value": 1}, "fixed")
        with self.assertRaises(FileExistsError): write_receipt(self.receipts, {"value": 2}, "fixed")
        self.assertEqual(json.loads(first.read_text())["value"], 1)

    def test_13_coder_selects_goose_without_running_fallback_on_pass(self):
        data = self.order()
        data.update(harness="coder", model="josie-qual-ornith-1.5-9b-q6")
        path = self.workspace / "coder.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        expected = ({"final_status": "PASS", "reason": "PASS", "harness": "goose"}, self.receipts / "goose.json")
        with patch("supervisor.run_job._execute_one", return_value=expected) as runner:
            receipt, _ = execute(path)
        self.assertEqual(receipt["harness"], "goose")
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[1]["harness"], "goose")
        self.assertEqual(runner.call_args.args[1]["model"], "josie-qual-ornith-1.5-9b-q6")

    def test_14_coder_falls_back_only_after_observed_goose_failure(self):
        data = self.order()
        data.update(harness="coder", model="josie-qual-ornith-1.5-9b-q6")
        path = self.workspace / "coder-fallback.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        primary_path = self.receipts / "primary.json"
        fallback_path = self.receipts / "fallback.json"
        results = [
            ({"final_status": "FAIL", "reason": "FAIL_TIMEOUT", "harness": "goose"}, primary_path),
            ({"final_status": "PASS", "reason": "PASS", "harness": "opencode",
              "acceptance_results": [{"passed": True}], "changed_files": []}, fallback_path),
        ]
        with patch("supervisor.run_job._execute_one", side_effect=results) as runner:
            receipt, aggregate_path = execute(path)
        self.assertEqual(runner.call_count, 2)
        self.assertTrue(receipt["fallback_occurred"])
        self.assertEqual(receipt["selected_harness"], "opencode")
        self.assertEqual(receipt["fallback_event"]["reason"], "FAIL_TIMEOUT")
        self.assertTrue(aggregate_path.is_file())

    def test_15_coder_falls_back_to_opencode_if_both_goose_attempts_fail(self):
        data = self.order()
        data.update(harness="coder", model="josie-qual-ornith-1.5-9b-q6")
        path = self.workspace / "coder-fallback-opencode.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        primary_path = self.receipts / "primary.json"
        fb1_path = self.receipts / "fb1.json"
        fb2_path = self.receipts / "fb2.json"
        results = [
            ({"final_status": "FAIL", "reason": "FAIL_TIMEOUT", "harness": "goose", "requested_model": "josie-qual-ornith-1.5-9b-q6"}, primary_path),
            ({"final_status": "FAIL", "reason": "FAIL_TIMEOUT", "harness": "goose", "requested_model": "qwen3:14b"}, fb1_path),
            ({"final_status": "PASS", "reason": "PASS", "harness": "opencode", "requested_model": "ollama/qwen3:14b",
              "acceptance_results": [{"passed": True}], "changed_files": []}, fb2_path),
        ]
        with patch("supervisor.run_job._execute_one", side_effect=results) as runner:
            receipt, aggregate_path = execute(path)
        self.assertEqual(runner.call_count, 3)
        self.assertEqual(runner.call_args_list[0].args[1]["model"], "josie-qual-ornith-1.5-9b-q6")
        self.assertEqual(runner.call_args_list[1].args[1]["model"], "qwen3:14b")
        self.assertEqual(runner.call_args_list[2].args[1]["harness"], "opencode")
        self.assertEqual(runner.call_args_list[2].args[1]["model"], "ollama/qwen3:14b")
        self.assertTrue(receipt["fallback_occurred"])
        self.assertEqual(receipt["selected_harness"], "opencode")
        self.assertEqual(receipt["fallback_harness"], "opencode")
        self.assertTrue(aggregate_path.is_file())

    def test_16_coder_falls_back_on_recoverable_worker_blocked_but_not_on_hard_blocker(self):
        data = self.order()
        data.update(harness="coder", model="josie-qual-ornith-1.5-9b-q6")
        path = self.workspace / "coder-recoverable.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        primary_path = self.receipts / "primary.json"
        fallback_path = self.receipts / "fallback.json"

        # Case A: Recoverable WORKER_BLOCKED triggers fallback
        results_recoverable = [
            ({"final_status": "BLOCKED", "reason": "WORKER_BLOCKED", "harness": "goose"}, primary_path),
            ({"final_status": "PASS", "reason": "PASS", "harness": "opencode",
              "acceptance_results": [{"passed": True}], "changed_files": []}, fallback_path),
        ]
        with patch("supervisor.run_job._execute_one", side_effect=results_recoverable) as runner:
            receipt, _ = execute(path)
        self.assertEqual(runner.call_count, 2)
        self.assertTrue(receipt["fallback_occurred"])

        # Case B: Hard blocker PREFLIGHT_BLOCKED does NOT trigger fallback
        results_hard = [
            ({"final_status": "BLOCKED", "reason": "PREFLIGHT_BLOCKED", "harness": "goose"}, primary_path),
        ]
        with patch("supervisor.run_job._execute_one", side_effect=results_hard) as runner:
            receipt, _ = execute(path)
        self.assertEqual(runner.call_count, 1)
        self.assertFalse(receipt.get("fallback_occurred", False))
        self.assertEqual(receipt["reason"], "PREFLIGHT_BLOCKED")


if __name__ == "__main__":
    unittest.main(verbosity=2)


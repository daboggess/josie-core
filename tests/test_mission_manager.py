from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mission_manager.dispatcher import DispatchError, MissionManager, MissionStateError
from mission_manager.models import PlanValidationError
from mission_manager.state import MissionStore
from mission_manager.worker_registry import department
from supervisor.receipts import write_receipt


ROOT = Path(r"D:\Josie")
TMP = ROOT / "tmp"


def plan(*, department="coding", allowed=None, dependencies=False):
    jobs = [{
        "job_id": "job-1", "title": "First", "department": department,
        "objective": "Make one bounded implementation with tests.", "dependencies": [],
        "workspace": str(ROOT), "allowed_changes": allowed or ["tmp/mm-target.txt"],
        "acceptance": [{"type": "file_exists", "path": "README.md"}], "timeout": 120,
    }]
    if dependencies:
        jobs.append({
            "job_id": "job-2", "title": "Second", "department": "coding",
            "objective": "Make the dependent bounded change.", "dependencies": ["job-1"],
            "workspace": str(ROOT), "allowed_changes": ["tmp/mm-second.txt"],
            "acceptance": [{"type": "file_exists", "path": "README.md"}], "timeout": 120,
        })
    return {"mission_id": "test-mission", "title": "Test Mission", "objective": "Exercise deterministic management.", "jobs": jobs}


class Harness:
    def __init__(self, base: Path, status="PASS", reason=None, narrative=None):
        self.base = base
        self.status = status
        self.reason = reason or status
        self.narrative = narrative
        self.calls = 0
        self.orders = []

    def __call__(self, order_path: Path):
        self.calls += 1
        order = json.loads(Path(order_path).read_text(encoding="utf-8"))
        self.orders.append(order)
        receipt = {
            "schema_version": "1", "supervisor_version": "test", "job_id": order["job_id"],
            "attempt": 1, "requested_model": order["model"], "elapsed_seconds": 4.5,
            "timed_out": self.reason == "FAIL_TIMEOUT", "worker_changed_paths": ["tmp/mm-target.txt"] if self.status == "PASS" else [],
            "scope_violations": [], "acceptance_results": [{"type": "file_exists", "passed": self.status == "PASS"}],
            "tool_activity": ["read", "edit"] if self.status == "PASS" else [], "worker_narrative": self.narrative,
            "exit_code": 0, "worker_launched": True, "blocker_reported": False,
            "side_effect_policy": {"denied_actions": []},
            "final_status": self.status, "reason": self.reason,
        }
        path = write_receipt(self.base / "receipts", receipt)
        return receipt, path


class MissionManagerTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TMP)
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def manager(self, harness=None):
        return MissionManager(self.base / "missions", receipt_directory=self.base / "receipts",
                              work_order_directory=self.base / "orders", supervisor_execute=harness)

    def test_01_valid_mission_parses(self):
        mission = self.manager().create(plan())
        self.assertEqual("PLANNED", mission["status"])
        self.assertEqual("READY", mission["jobs"][0]["status"])

    def test_02_malformed_mission_rejected(self):
        broken = plan()
        broken["jobs"][0]["dependencies"] = ["missing"]
        with self.assertRaises(PlanValidationError):
            self.manager().create(broken)

    def test_03_dependency_ordering_works(self):
        mission = self.manager().create(plan(dependencies=True))
        self.assertEqual(["READY", "WAITING"], [job["status"] for job in mission["jobs"]])

    def test_04_unavailable_department_cannot_dispatch(self):
        manager = self.manager()
        manager.create(plan(department="research"))
        with self.assertRaisesRegex(DispatchError, "DEPARTMENT_UNAVAILABLE"):
            manager.dispatch_next("test-mission")

    def test_05_ready_job_dispatches_only_once(self):
        harness = Harness(self.base)
        manager = self.manager(harness)
        manager.create(plan())
        manager.dispatch_next("test-mission")
        with self.assertRaises(DispatchError):
            manager.dispatch_next("test-mission")
        self.assertEqual(1, harness.calls)

    def test_06_pass_receipt_advances_dependency(self):
        manager = self.manager(Harness(self.base))
        manager.create(plan(dependencies=True))
        mission = manager.dispatch_next("test-mission")
        self.assertEqual(["PASS", "READY"], [job["status"] for job in mission["jobs"]])

    def test_07_fail_receipt_does_not_advance_dependency(self):
        manager = self.manager(Harness(self.base, "FAIL", "FAIL_ACCEPTANCE"))
        manager.create(plan(dependencies=True))
        mission = manager.dispatch_next("test-mission")
        self.assertEqual(["FAIL", "BLOCKED"], [job["status"] for job in mission["jobs"]])

    def test_08_mission_cannot_complete_without_all_required_pass_receipts(self):
        manager = self.manager()
        manager.create(plan())
        mission = manager.load("test-mission")
        mission["jobs"][0]["status"] = "PASS"
        mission["jobs"][0]["receipt_ref"] = "invented.json"
        manager.store.save(mission)
        with self.assertRaisesRegex(MissionStateError, "lacks authoritative PASS evidence"):
            manager.load("test-mission")

    def test_09_worker_narrative_cannot_set_pass(self):
        manager = self.manager(Harness(self.base, "FAIL", "FAIL_ACCEPTANCE", narrative="STATUS: PASS"))
        manager.create(plan())
        mission = manager.dispatch_next("test-mission")
        self.assertEqual("FAIL", mission["jobs"][0]["status"])

    def test_10_receipt_final_status_controls_job_result(self):
        manager = self.manager(Harness(self.base, "PASS", narrative="I failed"))
        manager.create(plan())
        mission = manager.dispatch_next("test-mission")
        self.assertEqual("PASS", mission["jobs"][0]["status"])

    def test_11_mission_state_survives_reload(self):
        manager = self.manager(Harness(self.base))
        manager.create(plan())
        manager.dispatch_next("test-mission")
        reloaded = self.manager().load("test-mission")
        self.assertEqual("PASS", reloaded["jobs"][0]["status"])

    def test_12_atomic_persistence_uses_replace_and_leaves_no_temp(self):
        store = MissionStore(self.base / "atomic")
        mission = {"mission_id": "atomic", "value": 1}
        with patch("mission_manager.state.os.replace", wraps=os.replace) as replace:
            store.save(mission)
        replace.assert_called_once()
        self.assertEqual([], list((self.base / "atomic").glob("*.tmp")))
        self.assertEqual(1, store.load("atomic")["value"])

    def test_13_duplicate_receipt_consumption_is_idempotent(self):
        manager = self.manager(Harness(self.base))
        manager.create(plan())
        mission = manager.dispatch_next("test-mission")
        receipt = Path(mission["jobs"][0]["receipt_ref"])
        before = manager.store.events_path("test-mission").read_text(encoding="utf-8")
        duplicate = manager.consume_receipt("test-mission", receipt, job_id="job-1")
        after = manager.store.events_path("test-mission").read_text(encoding="utf-8")
        self.assertEqual(1, len(duplicate["receipt_refs"]))
        self.assertEqual(before, after)

    def test_14_fail_timeout_records_adaptation_observation(self):
        manager = self.manager(Harness(self.base, "FAIL", "FAIL_TIMEOUT"))
        manager.create(plan())
        mission = manager.dispatch_next("test-mission")
        proposals = {item["possible_adaptation"] for item in mission["adaptation_observations"]}
        self.assertIn("REVIEW_REQUIRED", proposals)
        self.assertIn("INCREASE_CONTEXT_PREPARATION", proposals)
        self.assertNotIn("DECOMPOSE_JOB", proposals)

    def test_15_oversized_coding_job_is_refused(self):
        manager = self.manager()
        manager.create(plan(allowed=["a", "b", "c", "d"]))
        with self.assertRaisesRegex(DispatchError, "JOB_TOO_LARGE_FOR_WORKER"):
            manager.dispatch_next("test-mission")
        mission = manager.load("test-mission")
        self.assertEqual(0, mission["jobs"][0]["attempts"])

    def test_16_timeout_is_not_automatically_increased(self):
        manager = self.manager(Harness(self.base, "FAIL", "FAIL_TIMEOUT"))
        manager.create(plan())
        mission = manager.dispatch_next("test-mission")
        self.assertEqual(120, mission["jobs"][0]["timeout"])

    def test_17_supervisor_authority_is_not_modified(self):
        authority = ROOT / "supervisor" / "authority.py"
        before = hashlib.sha256(authority.read_bytes()).hexdigest()
        manager = self.manager(Harness(self.base))
        manager.create(plan())
        manager.dispatch_next("test-mission")
        self.assertEqual(before, hashlib.sha256(authority.read_bytes()).hexdigest())

    def test_18_progress_display_matches_receipt_state(self):
        manager = self.manager(Harness(self.base))
        manager.create(plan(dependencies=True))
        manager.dispatch_next("test-mission")
        output = manager.status("test-mission")["human"]
        self.assertEqual("Test Mission - 1/2 complete\n[PASS] First\n[READY] Second", output)

    def test_19_job_prompt_scope_and_acceptance_survive_translation(self):
        harness = Harness(self.base)
        manager = self.manager(harness)
        source = plan()
        source["jobs"][0]["objective"] = "Seal fields: principal_id, issuer, created_at, provenance"
        source["jobs"][0]["first_action"] = "Inspect the target, then create it."
        source["jobs"][0]["allowed_changes"] = ["dbot/contracts.py"]
        source["jobs"][0]["acceptance"] = [{"type": "command", "argv": [str(ROOT / ".venv/Scripts/python.exe"), "-m", "py_compile", "dbot/contracts.py"]}]
        manager.create(source)
        manager.dispatch_next("test-mission")
        order = harness.orders[0]
        self.assertEqual(source["jobs"][0]["objective"], order["objective"])
        self.assertEqual(source["jobs"][0]["first_action"], order["first_action"])
        self.assertEqual(["dbot/contracts.py"], order["allowed_changed_paths"])
        self.assertEqual(source["jobs"][0]["acceptance"], order["acceptance"])

    def test_20_evidenced_retry_is_bounded_and_preserves_failed_receipt(self):
        harness = Harness(self.base, "FAIL", "FAIL_ACCEPTANCE", narrative="STATUS: PASS")
        manager = self.manager(harness)
        manager.create(plan(dependencies=True))
        failed = manager.dispatch_next("test-mission")
        original_receipt = failed["jobs"][0]["receipt_ref"]
        retryable = manager.authorize_premature_stop_retry(
            "test-mission", "job-1", updated_objective="Complete requirements retained.",
            first_action="Inspect the target, then edit it.")
        self.assertEqual("READY", retryable["jobs"][0]["status"])
        self.assertEqual("WAITING", retryable["jobs"][1]["status"])
        self.assertEqual(original_receipt, retryable["jobs"][0]["attempt_history"][0]["path"])
        second_failure = manager.dispatch_next("test-mission")
        self.assertEqual(2, second_failure["jobs"][0]["attempts"])
        with self.assertRaisesRegex(DispatchError, "bounded mission retry limit"):
            manager.authorize_premature_stop_retry("test-mission", "job-1")
        self.assertEqual(120, second_failure["jobs"][0]["timeout"])

    def test_21_primary_worker_remains_qwen_and_fallback_is_explicit(self):
        self.assertEqual("ollama/qwen3:14b", department("coding")["model"])
        harness = Harness(self.base)
        manager = self.manager(harness)
        manager.create(plan())
        manager.dispatch_next("test-mission")
        self.assertEqual("ollama/qwen3:14b", harness.orders[0]["model"])
        self.assertNotIn("pending_fallback_model", manager.load("test-mission")["jobs"][0])

    def test_22_explicit_fallback_preserves_job_contract_and_records_model(self):
        failing = Harness(self.base, "FAIL", "FAIL_TIMEOUT")
        manager = self.manager(failing)
        source = plan(dependencies=True)
        manager.create(source)
        failed = manager.dispatch_next("test-mission")
        old_receipt = failed["jobs"][0]["receipt_ref"]
        manager.authorize_fallback_retry("test-mission", "gemma4:12b")
        passing = Harness(self.base)
        manager._execute = passing
        mission = manager.dispatch_next("test-mission")
        order = passing.orders[0]
        job = mission["jobs"][0]
        self.assertEqual("ollama/gemma4:12b", order["model"])
        self.assertEqual(source["jobs"][0]["allowed_changes"], order["allowed_changed_paths"])
        self.assertEqual(source["jobs"][0]["acceptance"], order["acceptance"])
        self.assertEqual(120, order["timeout_seconds"])
        self.assertEqual(1, order["max_attempts"])
        self.assertEqual("ollama/gemma4:12b", job["receipt_evidence"]["model"])
        self.assertEqual(1, job["fallback_attempts"])
        self.assertEqual(old_receipt, job["attempt_history"][0]["path"])

    def test_23_fallback_is_single_attempt_and_does_not_trigger_model_roulette(self):
        failing = Harness(self.base, "FAIL", "FAIL_TIMEOUT")
        manager = self.manager(failing)
        manager.create(plan())
        manager.dispatch_next("test-mission")
        manager.authorize_fallback_retry("test-mission", "gemma4:12b")
        manager.dispatch_next("test-mission")
        mission = manager.load("test-mission")
        self.assertEqual(["ollama/qwen3:14b", "ollama/gemma4:12b"],
                         mission["jobs"][0]["dispatch_models"])
        with self.assertRaisesRegex(DispatchError, "bounded fallback retry limit"):
            manager.authorize_fallback_retry("test-mission", "gemma4:12b")
        self.assertEqual(2, failing.calls)

    def test_24_unknown_fallback_is_refused_without_dispatch(self):
        failing = Harness(self.base, "FAIL", "FAIL_TIMEOUT")
        manager = self.manager(failing)
        manager.create(plan())
        manager.dispatch_next("test-mission")
        with self.assertRaisesRegex(DispatchError, "not allowed"):
            manager.authorize_fallback_retry("test-mission", "another-model")
        self.assertEqual(1, failing.calls)


    def test_25_goose_primary_opencode_fallback_routing_and_recoverable_blocker(self):
        dep = department("coding")
        self.assertIn("Goose", dep["harness"])
        self.assertIn("OpenCode", dep["harness"])

        # Default order harness is coder (Goose primary, OpenCode fallback)
        harness = Harness(self.base)
        manager = self.manager(harness)
        manager.create(plan())
        manager.dispatch_next("test-mission")
        self.assertEqual("coder", harness.orders[0]["harness"])

        # Recoverable blocker WORKER_BLOCKED permits fallback retry
        failing = Harness(self.base, "BLOCKED", "WORKER_BLOCKED")
        manager_fail = self.manager(failing)
        source = plan()
        source["mission_id"] = "mission-recoverable"
        manager_fail.create(source)
        manager_fail.dispatch_next("mission-recoverable")
        retryable = manager_fail.authorize_fallback_retry("mission-recoverable", "gemma4:12b")
        self.assertEqual("READY", retryable["jobs"][0]["status"])

        # Hard blocker PREFLIGHT_BLOCKED refuses fallback retry
        hard = Harness(self.base, "BLOCKED", "PREFLIGHT_BLOCKED")
        manager_hard = self.manager(hard)
        source2 = plan()
        source2["mission_id"] = "mission-hard"
        manager_hard.create(source2)
        manager_hard.dispatch_next("mission-hard")
        with self.assertRaisesRegex(DispatchError, "hard blocker cannot be retried"):
            manager_hard.authorize_fallback_retry("mission-hard", "gemma4:12b")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter, SupervisorResult
from campaign_manager.constants import CampaignStatus, JobState
from campaign_manager.manager import CampaignManager
from mission_manager.campaign_bridge import CampaignBridge, MissionState
from mission_manager.dispatcher import DispatchError, MissionManager
from mission_manager.ingress import continue_mission, mission_status, submit_mission
from supervisor.receipts import write_receipt


ROOT = Path(r"D:\Josie")
TMP = ROOT / "tmp"


class DeterministicSupervisorHarness:
    """Deterministic Supervisor execution harness recording call counts and writing receipts."""

    def __init__(self, receipt_directory: Path, *, status: str = "PASS", reason: str | None = None, narrative: str | None = None):
        self.receipt_directory = Path(receipt_directory)
        self.status = status
        self.reason = reason or status
        self.narrative = narrative
        self.calls = 0
        self.dispatched_orders: list[dict] = []
        self.generated_receipts: list[dict] = []

    def __call__(self, order_path: Path) -> tuple[dict, Path]:
        self.calls += 1
        order = json.loads(Path(order_path).read_text(encoding="utf-8"))
        self.dispatched_orders.append(order)
        receipt = {
            "schema_version": "1",
            "supervisor_version": "0.2.1-e2e-test",
            "job_id": order["job_id"],
            "attempt": 1,
            "requested_model": order["model"],
            "elapsed_seconds": 2.5,
            "timed_out": False,
            "worker_changed_paths": list(order.get("allowed_changed_paths", [])),
            "scope_violations": [],
            "acceptance_results": [
                {"type": check.get("type", "custom"), "passed": (self.status == "PASS")}
                for check in order.get("acceptance", [])
            ] or [{"type": "default_check", "passed": (self.status == "PASS")}],
            "tool_activity": ["read", "edit"],
            "worker_narrative": self.narrative or f"Worker execution report for {order['job_id']}",
            "exit_code": 0 if self.status == "PASS" else 1,
            "worker_launched": True,
            "blocker_reported": False,
            "side_effect_policy": {"denied_actions": []},
            "final_status": self.status,
            "reason": self.reason,
        }
        receipt_path = write_receipt(self.receipt_directory, receipt)
        self.generated_receipts.append(receipt)
        return receipt, receipt_path


class TestMissionManagerLifecycleE2E(unittest.TestCase):
    """E2E qualification of the Mission Manager control plane (front-door, state, dispatcher, idempotency)."""

    def setUp(self) -> None:
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=TMP)
        self.base = Path(self.temp_dir.name)
        self.missions_dir = self.base / "data" / "private" / "missions"
        self.receipts_dir = self.base / "data" / "private" / "supervisor-local-code"
        self.orders_dir = self.base / "data" / "private" / "supervisor-work-orders"
        self.missions_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.orders_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy target files inside temporary workspace
        (self.base / "file_a.txt").write_text("initial a", encoding="utf-8")
        (self.base / "file_b.txt").write_text("initial b", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_two_step_plan(self, mission_id: str = "mission-e2e-001") -> dict:
        return {
            "mission_id": mission_id,
            "title": "E2E Autonomous Lifecycle Mission",
            "objective": "Prove full 9-point control-plane qualification.",
            "jobs": [
                {
                    "job_id": "job-step-1",
                    "title": "Step 1: Foundation",
                    "department": "coding",
                    "objective": "Build foundation artifact.",
                    "dependencies": [],
                    "workspace": str(self.base),
                    "allowed_changes": ["file_a.txt"],
                    "acceptance": [{"type": "file_exists", "path": "file_a.txt"}],
                    "timeout": 60,
                },
                {
                    "job_id": "job-step-2",
                    "title": "Step 2: Integration",
                    "department": "coding",
                    "objective": "Build dependent artifact.",
                    "dependencies": ["job-step-1"],
                    "workspace": str(self.base),
                    "allowed_changes": ["file_b.txt"],
                    "acceptance": [{"type": "file_exists", "path": "file_b.txt"}],
                    "timeout": 60,
                },
            ],
        }

    def test_full_autonomous_mission_lifecycle(self) -> None:
        """Covers all 9 acceptance criteria for MissionManager control plane."""
        mission_id = "mission-e2e-001"
        plan = self.make_two_step_plan(mission_id)

        # 1. Be submitted through the Mission Manager/front-door path.
        submit_res = submit_mission(plan, project_root=self.base)
        self.assertEqual(submit_res["schema_version"], 1)
        self.assertEqual(submit_res["stop_reason"], "SUBMITTED")

        # 2. Receive a durable mission identity.
        self.assertEqual(submit_res["mission_id"], mission_id)
        self.assertEqual(submit_res["mission_status"], "PLANNED")

        # 3. Persist its state and work information.
        persisted_file = self.missions_dir / f"{mission_id}.json"
        events_file = self.missions_dir / f"{mission_id}.events.jsonl"
        self.assertTrue(persisted_file.is_file(), "Mission state file must exist on disk")
        self.assertTrue(events_file.is_file(), "Mission events file must exist on disk")

        saved_data = json.loads(persisted_file.read_text(encoding="utf-8"))
        self.assertEqual(saved_data["mission_id"], mission_id)
        self.assertEqual(len(saved_data["jobs"]), 2)
        self.assertEqual(saved_data["jobs"][0]["status"], "READY")
        self.assertEqual(saved_data["jobs"][1]["status"], "WAITING")

        events_content = events_file.read_text(encoding="utf-8")
        self.assertIn('"event": "MISSION_CREATED"', events_content)

        # 4. Be dispatched through the existing Mission Manager dispatcher.
        # 5. Record machine-readable execution/receipt evidence.
        # 6. Reach a terminal state based on machine evidence rather than worker narrative.
        harness = DeterministicSupervisorHarness(
            self.receipts_dir,
            status="PASS",
            narrative="Worker narrative claims success: ALL DONE",
        )

        dispatch_res = continue_mission(
            mission_id,
            project_root=self.base,
            supervisor_execute=harness,
        )

        # Both jobs dispatched and completed
        self.assertEqual(dispatch_res["mission_status"], "COMPLETE")
        self.assertEqual(dispatch_res["stop_reason"], "COMPLETE")
        self.assertEqual(dispatch_res["jobs_dispatched"], ["job-step-1", "job-step-2"])
        self.assertEqual(dispatch_res["progress"]["completed"], 2)
        self.assertEqual(dispatch_res["progress"]["total"], 2)

        # Exactly 1 execution per logical work item (total 2 executions for 2 jobs)
        self.assertEqual(harness.calls, 2, "Each job must execute exactly once")

        # Verify durable machine receipts were written to disk
        receipt_files = list(self.receipts_dir.glob("*.json"))
        self.assertEqual(len(receipt_files), 2, "Expected 2 machine receipt files")

        # Verify mission persisted state updated to COMPLETE with authoritative receipts
        reloaded_data = json.loads(persisted_file.read_text(encoding="utf-8"))
        self.assertEqual(reloaded_data["status"], "COMPLETE")
        self.assertEqual(len(reloaded_data["receipt_refs"]), 2)
        self.assertEqual(reloaded_data["jobs"][0]["status"], "PASS")
        self.assertEqual(reloaded_data["jobs"][1]["status"], "PASS")
        self.assertIsNotNone(reloaded_data["jobs"][0]["receipt_evidence"])
        self.assertIsNotNone(reloaded_data["jobs"][1]["receipt_evidence"])

        # 7. Be queried afterward and return the durable terminal result.
        status_res = mission_status(mission_id, project_root=self.base)
        self.assertEqual(status_res["mission_status"], "COMPLETE")
        self.assertEqual(status_res["stop_reason"], "STATUS_ONLY")
        self.assertEqual(status_res["jobs_dispatched"], [])
        self.assertEqual(status_res["progress"]["completed"], 2)
        self.assertEqual(status_res["latest_authoritative_receipt"], dispatch_res["latest_authoritative_receipt"])
        self.assertEqual(harness.calls, 2, "Status query must not invoke worker execution")

        # 8. Survive reconstruction/restart of the Mission Manager process without losing authoritative mission state.
        del dispatch_res
        del status_res
        # Instantiate brand-new manager instance simulating a cold process restart
        reconstructed_manager = MissionManager(
            self.missions_dir,
            receipt_directory=self.receipts_dir,
            work_order_directory=self.orders_dir,
        )
        loaded_mission = reconstructed_manager.load(mission_id)
        self.assertEqual(loaded_mission["status"], "COMPLETE")
        self.assertEqual(loaded_mission["progress"]["completed"], 2)
        self.assertEqual(len(loaded_mission["receipt_refs"]), 2)
        self.assertEqual(loaded_mission["jobs"][0]["receipt_evidence"]["final_status"], "PASS")
        self.assertEqual(loaded_mission["jobs"][1]["receipt_evidence"]["final_status"], "PASS")

        # 9. Avoid duplicate execution when the same persisted mission is resumed or queried again.
        # Re-running continue_mission on completed mission must execute 0 times
        resume_res = continue_mission(
            mission_id,
            project_root=self.base,
            supervisor_execute=harness,
        )
        self.assertEqual(resume_res["mission_status"], "COMPLETE")
        self.assertEqual(resume_res["stop_reason"], "COMPLETE")
        self.assertEqual(resume_res["jobs_dispatched"], [])
        self.assertFalse(resume_res["supervisor_invoked"])
        self.assertEqual(harness.calls, 2, "Duplicate resume must not trigger execution")

        # Re-submitting the plan must also be idempotent
        resubmit_res = submit_mission(plan, project_root=self.base)
        self.assertEqual(resubmit_res["stop_reason"], "ALREADY_EXISTS")
        self.assertEqual(resubmit_res["mission_status"], "COMPLETE")
        self.assertEqual(harness.calls, 2, "Duplicate submit must not trigger execution")

    def test_worker_narrative_cannot_override_machine_failure(self) -> None:
        """Terminal state is governed strictly by machine evidence; worker claiming PASS on FAIL is rejected."""
        mission_id = "mission-narrative-test"
        plan = {
            "mission_id": mission_id,
            "title": "Narrative Rejection Mission",
            "objective": "Verify worker narrative does not grant PASS.",
            "jobs": [
                {
                    "job_id": "job-failing-check",
                    "title": "Failing Job",
                    "department": "coding",
                    "objective": "Run check that fails acceptance.",
                    "dependencies": [],
                    "workspace": str(self.base),
                    "allowed_changes": ["file_a.txt"],
                    "acceptance": [{"type": "file_exists", "path": "nonexistent.txt"}],
                    "timeout": 60,
                }
            ],
        }

        submit_mission(plan, project_root=self.base)

        # Harness produces FAIL with deceptive worker narrative claiming success
        failing_harness = DeterministicSupervisorHarness(
            self.receipts_dir,
            status="FAIL",
            reason="FAIL_ACCEPTANCE",
            narrative="STATUS: PASS - 100% COMPLETE AND ACCEPTED BY WORKER",
        )

        outcome = continue_mission(
            mission_id,
            project_root=self.base,
            supervisor_execute=failing_harness,
        )

        # Terminal state must be FAILED, not COMPLETE
        self.assertEqual(outcome["mission_status"], "FAILED")
        self.assertEqual(outcome["stop_reason"], "FAIL_ACCEPTANCE")
        self.assertEqual(failing_harness.calls, 1)

        # Query afterward confirms durable failure
        status_res = mission_status(mission_id, project_root=self.base)
        self.assertEqual(status_res["mission_status"], "FAILED")

        # Cold reload confirms authoritative failure preserved across restart
        new_manager = MissionManager(
            self.missions_dir,
            receipt_directory=self.receipts_dir,
            work_order_directory=self.orders_dir,
        )
        loaded = new_manager.load(mission_id)
        self.assertEqual(loaded["status"], "FAILED")
        self.assertEqual(loaded["jobs"][0]["status"], "FAIL")


class TestHopperCampaignBridgeLifecycleE2E(unittest.TestCase):
    """E2E qualification of the Hopper / CampaignBridge control plane."""

    def setUp(self) -> None:
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=TMP)
        self.base = Path(self.temp_dir.name)
        self.missions_db = self.base / "data" / "missions.db"
        self.campaigns_db = self.base / "data" / "campaigns.db"
        self.receipt_dir = self.base / "data" / "mission_receipts"
        self.sup_receipt_dir = self.base / "data" / "private" / "supervisor-local-code"
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        self.sup_receipt_dir.mkdir(parents=True, exist_ok=True)

        self.fake_adapter = FakeSupervisorAdapter()
        self.campaign_manager = CampaignManager(
            db_path=self.campaigns_db,
            adapter=self.fake_adapter,
            lease_duration_seconds=30,
        )
        self.bridge = CampaignBridge(
            db_path=self.missions_db,
            campaign_manager=self.campaign_manager,
            receipt_dir=self.receipt_dir,
        )

        (self.base / "hopper_a.txt").write_text("data a", encoding="utf-8")
        (self.base / "hopper_b.txt").write_text("data b", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_hopper_campaign_bridge_lifecycle_and_reconstruction(self) -> None:
        """Verifies submission, durable identity, DAG dispatch, machine receipts, reconstruction, and idempotency."""
        mission_id = "hopper-e2e-001"
        plan = {
            "mission_id": mission_id,
            "title": "Hopper E2E Mission",
            "objective": "Validate Hopper control plane lifecycle.",
            "jobs": [
                {
                    "job_id": "hopper-step-1",
                    "title": "Step 1",
                    "objective": "Create artifact A",
                    "workspace": str(self.base),
                    "allowed_changes": ["hopper_a.txt"],
                    "acceptance": [{"type": "file_exists", "path": "hopper_a.txt"}],
                    "dependencies": [],
                    "timeout_seconds": 30,
                    "max_attempts": 1,
                    "retry_safe": True,
                    "receipt_destination": str(self.sup_receipt_dir),
                },
                {
                    "job_id": "hopper-step-2",
                    "title": "Step 2",
                    "objective": "Create artifact B",
                    "workspace": str(self.base),
                    "allowed_changes": ["hopper_b.txt"],
                    "acceptance": [{"type": "file_exists", "path": "hopper_b.txt"}],
                    "dependencies": ["hopper-step-1"],
                    "timeout_seconds": 30,
                    "max_attempts": 1,
                    "retry_safe": True,
                    "receipt_destination": str(self.sup_receipt_dir),
                },
            ],
        }

        # 1. Submission through Hopper / CampaignBridge
        sub = self.bridge.submit_mission(plan)
        self.assertEqual(sub["status"], MissionState.SUBMITTED)

        # 2. Durable identity in both missions.db and campaigns.db
        self.assertEqual(sub["mission_id"], mission_id)
        self.assertEqual(sub["campaign_id"], f"mission-{mission_id}")

        # 3. Persistent state on disk (SQLite DBs)
        self.assertTrue(self.missions_db.is_file())
        self.assertTrue(self.campaigns_db.is_file())

        # Configure adapter for deterministic PASS
        self.fake_adapter.set_result(
            f"mission-{mission_id}-hopper-step-1",
            SupervisorResult(
                final_status="PASS",
                reason="ACCEPTANCE_PASSED",
                receipt={"final_status": "PASS", "job_id": f"mission-{mission_id}-hopper-step-1-1"},
                receipt_id="rcpt-hopper-1",
            ),
        )
        self.fake_adapter.set_result(
            f"mission-{mission_id}-hopper-step-2",
            SupervisorResult(
                final_status="PASS",
                reason="ACCEPTANCE_PASSED",
                receipt={"final_status": "PASS", "job_id": f"mission-{mission_id}-hopper-step-2-1"},
                receipt_id="rcpt-hopper-2",
            ),
        )

        # 4, 5, 6. Dispatch and reach terminal state via machine evidence
        res = self.bridge.run_mission(mission_id)
        self.assertEqual(res["status"], MissionState.COMPLETED)
        self.assertEqual(res["campaign_status"], CampaignStatus.COMPLETED)

        # Exactly 1 call per job (total 2)
        self.assertEqual(len(self.fake_adapter.call_history), 2)

        # Durable mission receipt written to disk
        receipt_file = self.receipt_dir / f"{mission_id}.json"
        self.assertTrue(receipt_file.is_file(), "Mission receipt JSON must exist")

        receipt_data = json.loads(receipt_file.read_text(encoding="utf-8"))
        self.assertEqual(receipt_data["final_verdict"], "COMPLETED")
        self.assertEqual(receipt_data["status_reason"], "ALL_JOBS_PASSED_MACHINE_ACCEPTANCE")
        self.assertEqual(len(receipt_data["jobs"]), 2)
        for j in receipt_data["jobs"]:
            self.assertEqual(j["state"], JobState.PASS)

        # 7. Query afterward
        status = self.bridge.get_mission_status(mission_id)
        self.assertEqual(status["status"], MissionState.COMPLETED)
        self.assertEqual(status["receipt_path"], str(receipt_file))

        # 8. Reconstruction / restart of bridge and manager
        del self.bridge
        del self.campaign_manager
        reconstructed_cm = CampaignManager(
            db_path=self.campaigns_db,
            adapter=self.fake_adapter,
            lease_duration_seconds=30,
        )
        reconstructed_bridge = CampaignBridge(
            db_path=self.missions_db,
            campaign_manager=reconstructed_cm,
            receipt_dir=self.receipt_dir,
        )

        recon_status = reconstructed_bridge.get_mission_status(mission_id)
        self.assertEqual(recon_status["status"], MissionState.COMPLETED)
        recon_receipt = reconstructed_bridge.get_mission_receipt(mission_id)
        self.assertEqual(recon_receipt["final_verdict"], "COMPLETED")

        # 9. Avoid duplicate execution on resume / re-query
        re_run = reconstructed_bridge.run_mission(mission_id)
        self.assertEqual(re_run["status"], MissionState.COMPLETED)
        self.assertEqual(len(self.fake_adapter.call_history), 2, "Re-run must not execute any jobs")

        re_sub = reconstructed_bridge.submit_mission(plan)
        self.assertEqual(re_sub["status"], MissionState.COMPLETED)
        self.assertEqual(len(self.fake_adapter.call_history), 2, "Re-submit must not execute any jobs")


if __name__ == "__main__":
    unittest.main()

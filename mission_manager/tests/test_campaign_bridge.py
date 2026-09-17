from __future__ import annotations

import inspect
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any

from campaign_manager.adapter import FakeSupervisorAdapter, SupervisorResult
from campaign_manager.constants import CampaignStatus, JobState
from campaign_manager.errors import CampaignNotFoundError
from campaign_manager.manager import CampaignManager
from campaign_manager.models import AttemptRecord, CampaignRecord, JobRecord
from campaign_manager.validation import validate_campaign_spec

from mission_manager.campaign_bridge import (
    BridgeAuthorityError,
    BridgeError,
    CampaignBridge,
    MissionNotFoundError,
    MissionState,
    MissionValidationError,
    plan_to_campaign_spec,
    validate_mission_plan,
)
from mission_manager.db import get_connection, init_db


class FakeCampaignManager:
    """Configurable fake CampaignManager for deterministic unit testing."""

    def __init__(self) -> None:
        self.campaigns: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.attempts: dict[str, list[AttemptRecord]] = {}
        self.created_specs: list[dict[str, Any]] = []

    def create_campaign(self, spec: dict[str, Any]) -> str:
        validate_campaign_spec(spec)
        cid = spec.get("campaign_id") or "camp-test-1"
        if cid in self.campaigns:
            raise ValueError(f"Campaign {cid} already exists")
        self.created_specs.append(spec)
        self.campaigns[cid] = {
            "campaign_id": cid,
            "name": spec["name"],
            "status": CampaignStatus.QUEUED,
            "spec": spec,
        }
        for j in spec["jobs"]:
            jid = j["job_id"]
            self.jobs[jid] = {
                "job_id": jid,
                "campaign_id": cid,
                "name": j["name"],
                "state": j.get("initial_state", JobState.QUEUED),
                "work_order": j["work_order"],
                "max_attempts": j["max_attempts"],
                "attempts_used": 0,
                "retry_safe": j["retry_safe"],
                "last_supervisor_request_id": None,
                "last_supervisor_receipt_id": None,
                "failure_reason": None,
            }
            self.attempts[jid] = []
        return cid

    def get_campaign(self, campaign_id: str) -> CampaignRecord:
        if campaign_id not in self.campaigns:
            raise CampaignNotFoundError(f"Campaign {campaign_id} not found")
        c = self.campaigns[campaign_id]
        return CampaignRecord(
            campaign_id=c["campaign_id"],
            name=c["name"],
            created_at="2026-09-13T12:00:00Z",
            updated_at="2026-09-13T12:00:00Z",
            status=c["status"],
            spec_json=json.dumps(c["spec"]),
        )

    def get_campaign_status(self, campaign_id: str) -> dict[str, Any]:
        c = self.get_campaign(campaign_id)
        c_jobs = [j for j in self.jobs.values() if j["campaign_id"] == campaign_id]
        counts = {
            JobState.PASS: sum(1 for j in c_jobs if j["state"] == JobState.PASS),
            JobState.RUNNING: sum(1 for j in c_jobs if j["state"] == JobState.RUNNING),
            JobState.QUEUED: sum(1 for j in c_jobs if j["state"] == JobState.QUEUED),
            JobState.BLOCKED: sum(1 for j in c_jobs if j["state"] == JobState.BLOCKED),
            JobState.WAITING_APPROVAL: sum(1 for j in c_jobs if j["state"] == JobState.WAITING_APPROVAL),
            JobState.FAIL: sum(1 for j in c_jobs if j["state"] == JobState.FAIL),
            JobState.RETRY: sum(1 for j in c_jobs if j["state"] == JobState.RETRY),
            JobState.CANCELLED: sum(1 for j in c_jobs if j["state"] == JobState.CANCELLED),
        }
        summary_order = [
            JobState.PASS, JobState.RUNNING, JobState.QUEUED, JobState.BLOCKED,
            JobState.WAITING_APPROVAL, JobState.FAIL, JobState.RETRY, JobState.CANCELLED
        ]
        summary_str = " | ".join(f"{st} {counts[st]}" for st in summary_order)
        return {
            "campaign_id": campaign_id,
            "name": c.name,
            "status": c.status,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
            "counts": counts,
            "summary": summary_str,
            "jobs": list(c_jobs),
        }

    def get_attempts(self, job_id: str) -> list[AttemptRecord]:
        return self.attempts.get(job_id, [])

    def run_campaign(self, campaign_id: str) -> dict[str, Any]:
        return self.get_campaign_status(campaign_id)

    def approve_job(self, job_id: str) -> None:
        if job_id in self.jobs:
            self.jobs[job_id]["state"] = JobState.QUEUED


class TestCampaignBridge(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="mission_test_")
        self.db_path = Path(self.tmp_dir) / "missions.db"
        self.receipt_dir = Path(self.tmp_dir) / "receipts"
        self.workspace = Path(self.tmp_dir) / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.fake_cm = FakeCampaignManager()
        self.bridge = CampaignBridge(
            db_path=self.db_path,
            campaign_manager=self.fake_cm,
            receipt_dir=self.receipt_dir,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _sample_plan(self) -> dict[str, Any]:
        return {
            "mission_id": "test-mission-01",
            "title": "Test Mission Title",
            "objective": "Verify bridge conversion and execution",
            "jobs": [
                {
                    "job_id": "job-a",
                    "title": "Job A Step",
                    "objective": "Create artifact A",
                    "workspace": str(self.workspace),
                    "allowed_changes": ["artifact_a.txt"],
                    "acceptance": [{"type": "file_exists", "path": "artifact_a.txt"}],
                    "dependencies": [],
                    "timeout_seconds": 60,
                    "max_attempts": 2,
                    "retry_safe": True,
                },
                {
                    "job_id": "job-b",
                    "title": "Job B Step",
                    "objective": "Create artifact B from A",
                    "workspace": str(self.workspace),
                    "allowed_changes": ["artifact_b.txt"],
                    "acceptance": [{"type": "file_exists", "path": "artifact_b.txt"}],
                    "dependencies": ["job-a"],
                    "timeout_seconds": 90,
                    "max_attempts": 1,
                    "retry_safe": False,
                },
            ],
        }

    def test_01_valid_mission_converts_to_valid_campaign_spec(self) -> None:
        plan = self._sample_plan()
        spec = plan_to_campaign_spec(plan)
        # Verify validate_campaign_spec accepts it without error
        validated = validate_campaign_spec(spec)
        self.assertEqual(validated["campaign_id"], "mission-test-mission-01")
        self.assertEqual(validated["name"], "Test Mission Title")
        self.assertEqual(len(validated["jobs"]), 2)

    def test_02_dependencies_map_exactly(self) -> None:
        plan = self._sample_plan()
        spec = plan_to_campaign_spec(plan)
        jobs = {j["job_id"]: j for j in spec["jobs"]}
        self.assertEqual(jobs["job-a"]["dependencies"], [])
        self.assertEqual(jobs["job-b"]["dependencies"], ["job-a"])

    def test_03_retry_policy_maps_exactly(self) -> None:
        plan = self._sample_plan()
        spec = plan_to_campaign_spec(plan)
        jobs = {j["job_id"]: j for j in spec["jobs"]}
        self.assertEqual(jobs["job-a"]["max_attempts"], 2)
        self.assertTrue(jobs["job-a"]["retry_safe"])
        self.assertEqual(jobs["job-b"]["max_attempts"], 1)
        self.assertFalse(jobs["job-b"]["retry_safe"])

    def test_04_allowed_paths_remain_unchanged(self) -> None:
        plan = self._sample_plan()
        spec = plan_to_campaign_spec(plan)
        jobs = {j["job_id"]: j for j in spec["jobs"]}
        self.assertEqual(jobs["job-a"]["work_order"]["allowed_changed_paths"], ["artifact_a.txt"])
        self.assertEqual(jobs["job-b"]["work_order"]["allowed_changed_paths"], ["artifact_b.txt"])

    def test_05_acceptance_checks_remain_unchanged(self) -> None:
        plan = self._sample_plan()
        spec = plan_to_campaign_spec(plan)
        jobs = {j["job_id"]: j for j in spec["jobs"]}
        self.assertEqual(jobs["job-a"]["work_order"]["acceptance"], [{"type": "file_exists", "path": "artifact_a.txt"}])
        self.assertEqual(jobs["job-b"]["work_order"]["acceptance"], [{"type": "file_exists", "path": "artifact_b.txt"}])

    def test_06_authority_sensitive_fields_not_broadened(self) -> None:
        plan = self._sample_plan()
        # Attempt to inject path traversal
        plan["jobs"][0]["allowed_changes"] = ["../escape.txt"]
        with self.assertRaises(MissionValidationError):
            validate_mission_plan(plan)

        # Attempt to inject absolute path
        plan["jobs"][0]["allowed_changes"] = ["/etc/passwd"]
        with self.assertRaises(MissionValidationError):
            validate_mission_plan(plan)

        # Attempt to inject drive colon
        plan["jobs"][0]["allowed_changes"] = [r"C:\windows\system32"]
        with self.assertRaises(MissionValidationError):
            validate_mission_plan(plan)

    def test_07_duplicate_mission_submission_is_idempotent(self) -> None:
        plan = self._sample_plan()
        res1 = self.bridge.submit_mission(plan)
        self.assertEqual(res1["status"], MissionState.SUBMITTED)
        self.assertEqual(res1["campaign_id"], "mission-test-mission-01")

        # Second submission must succeed idempotently
        res2 = self.bridge.submit_mission(plan)
        self.assertEqual(res2["status"], MissionState.SUBMITTED)
        self.assertEqual(res2["campaign_id"], "mission-test-mission-01")

    def test_08_duplicate_submission_does_not_duplicate_campaign_or_jobs(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)
        self.bridge.submit_mission(plan)

        # Check FakeCampaignManager only received 1 creation call
        self.assertEqual(len(self.fake_cm.created_specs), 1)

        # Check missions.db only has 1 record
        conn = get_connection(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM missions WHERE mission_id = ?", ("test-mission-01",))
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_09_mission_never_marks_completed_from_worker_prose_alone(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        # Fake campaign has prose claiming success, but campaign status is RUNNING
        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.RUNNING
        self.fake_cm.jobs["job-a"]["state"] = JobState.RUNNING
        self.fake_cm.jobs["job-a"]["worker_prose"] = "Everything passed perfectly! 100% complete."

        status = self.bridge.reconcile_mission("test-mission-01")
        self.assertNotEqual(status["status"], MissionState.COMPLETED)
        self.assertEqual(status["status"], MissionState.RUNNING)

    def test_10_campaign_pass_evidence_maps_to_mission_completed(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        # Set all jobs to PASS and campaign to COMPLETED
        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.COMPLETED
        self.fake_cm.jobs["job-a"]["state"] = JobState.PASS
        self.fake_cm.jobs["job-b"]["state"] = JobState.PASS

        status = self.bridge.reconcile_mission("test-mission-01")
        self.assertEqual(status["status"], MissionState.COMPLETED)

    def test_11_campaign_failure_maps_correctly(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.FAILED
        self.fake_cm.jobs["job-a"]["state"] = JobState.FAIL

        status = self.bridge.reconcile_mission("test-mission-01")
        self.assertEqual(status["status"], MissionState.FAILED)

    def test_12_campaign_blocked_maps_correctly(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.BLOCKED
        self.fake_cm.jobs["job-a"]["state"] = JobState.FAIL
        self.fake_cm.jobs["job-b"]["state"] = JobState.BLOCKED

        status = self.bridge.reconcile_mission("test-mission-01")
        self.assertEqual(status["status"], MissionState.BLOCKED)

    def test_13_waiting_approval_maps_correctly(self) -> None:
        plan = self._sample_plan()
        plan["jobs"][0]["requires_approval"] = True
        self.bridge.submit_mission(plan)

        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.BLOCKED
        self.fake_cm.jobs["job-a"]["state"] = JobState.WAITING_APPROVAL

        status = self.bridge.reconcile_mission("test-mission-01")
        self.assertEqual(status["status"], MissionState.WAITING_APPROVAL)

    def test_14_independent_runnable_branch_not_falsely_marked_blocked(self) -> None:
        plan = self._sample_plan()
        # Add Job C: independent
        plan["jobs"].append({
            "job_id": "job-c",
            "title": "Job C",
            "objective": "Independent task",
            "workspace": str(self.workspace),
            "allowed_changes": ["c.txt"],
            "acceptance": [{"type": "file_exists", "path": "c.txt"}],
            "dependencies": [],
            "timeout_seconds": 60,
            "max_attempts": 1,
            "retry_safe": True,
        })
        self.bridge.submit_mission(plan)

        # Job A failed, Job B blocked by A, but Job C is still RUNNING
        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.RUNNING
        self.fake_cm.jobs["job-a"]["state"] = JobState.FAIL
        self.fake_cm.jobs["job-b"]["state"] = JobState.BLOCKED
        self.fake_cm.jobs["job-c"]["state"] = JobState.RUNNING

        status = self.bridge.reconcile_mission("test-mission-01")
        # Mission must NOT be BLOCKED while Job C is actively running
        self.assertEqual(status["status"], MissionState.RUNNING)

    def test_15_mission_receipt_references_actual_campaign_id(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.COMPLETED
        self.fake_cm.jobs["job-a"]["state"] = JobState.PASS
        self.fake_cm.jobs["job-b"]["state"] = JobState.PASS

        self.bridge.reconcile_mission("test-mission-01")
        receipt = self.bridge.get_mission_receipt("test-mission-01")

        self.assertEqual(receipt["mission_id"], "test-mission-01")
        self.assertEqual(receipt["campaign_id"], "mission-test-mission-01")
        self.assertEqual(receipt["final_verdict"], MissionState.COMPLETED)

    def test_16_mission_receipt_references_actual_supervisor_receipt_ids(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.COMPLETED
        self.fake_cm.jobs["job-a"]["state"] = JobState.PASS
        self.fake_cm.jobs["job-a"]["last_supervisor_receipt_id"] = "rcpt-sup-001"
        self.fake_cm.jobs["job-b"]["state"] = JobState.PASS
        self.fake_cm.jobs["job-b"]["last_supervisor_receipt_id"] = "rcpt-sup-002"

        self.fake_cm.attempts["job-a"] = [
            AttemptRecord(
                attempt_id="att-1",
                job_id="job-a",
                campaign_id="mission-test-mission-01",
                attempt_number=1,
                supervisor_job_id="mission-test-mission-01-job-a-1",
                supervisor_request_id="req-1",
                supervisor_receipt_id="rcpt-sup-001",
                supervisor_receipt_path="D:/Josie/data/receipts/rcpt-sup-001.json",
                status="PASS",
                failure_reason=None,
                started_at="2026-09-13T12:00:00Z",
                completed_at="2026-09-13T12:01:00Z",
                created_at="2026-09-13T12:00:00Z",
            )
        ]

        self.bridge.reconcile_mission("test-mission-01")
        receipt = self.bridge.get_mission_receipt("test-mission-01")

        audit_receipts = receipt["audit_trail"]["supervisor_receipt_ids"]
        self.assertIn("rcpt-sup-001", audit_receipts)
        self.assertIn("rcpt-sup-002", audit_receipts)

    def test_17_invalid_mission_fails_before_partial_durable_creation(self) -> None:
        plan = self._sample_plan()
        plan["jobs"][0]["workspace"] = "D:/NonExistent/Workspace/Directory/12345"

        with self.assertRaises(MissionValidationError):
            self.bridge.submit_mission(plan)

        # Ensure nothing was inserted into missions.db
        conn = get_connection(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM missions")
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()

    def test_18_dependency_validation_failure_leaves_no_fake_mission(self) -> None:
        plan = self._sample_plan()
        # Introduce cycle: A -> B -> A
        plan["jobs"][0]["dependencies"] = ["job-b"]

        with self.assertRaises(MissionValidationError):
            self.bridge.submit_mission(plan)

        conn = get_connection(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM missions")
        self.assertEqual(cursor.fetchone()[0], 0)
        conn.close()

    def test_19_restart_reopen_preserves_mission_campaign_mapping(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        # Simulate fresh bridge instance (e.g. process restart)
        reopened_bridge = CampaignBridge(
            db_path=self.db_path,
            campaign_manager=self.fake_cm,
            receipt_dir=self.receipt_dir,
        )

        mission = reopened_bridge.get_mission("test-mission-01")
        self.assertEqual(mission["campaign_id"], "mission-test-mission-01")
        self.assertEqual(mission["status"], MissionState.SUBMITTED)

    def test_20_reconciliation_after_restart_derives_state_from_durable_campaign(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)

        # Update underlying campaign while bridge is "offline"
        self.fake_cm.campaigns["mission-test-mission-01"]["status"] = CampaignStatus.COMPLETED
        self.fake_cm.jobs["job-a"]["state"] = JobState.PASS
        self.fake_cm.jobs["job-b"]["state"] = JobState.PASS

        # New bridge instance after restart
        reopened_bridge = CampaignBridge(
            db_path=self.db_path,
            campaign_manager=self.fake_cm,
            receipt_dir=self.receipt_dir,
        )

        status = reopened_bridge.reconcile_mission("test-mission-01")
        self.assertEqual(status["status"], MissionState.COMPLETED)
        self.assertTrue(Path(status["receipt_path"]).exists())

    def test_21_mission_cannot_directly_dispatch_worker(self) -> None:
        # Verify CampaignBridge source code contains no worker execution imports or methods
        bridge_source = inspect.getsource(CampaignBridge)
        for prohibited in ["subprocess.Popen", "opencode", "goose", "ollama", "launch_worker"]:
            self.assertNotIn(
                prohibited,
                bridge_source.lower(),
                f"Prohibited worker invocation '{prohibited}' found in CampaignBridge source",
            )
        self.assertFalse(hasattr(self.bridge, "dispatch_worker"))
        self.assertFalse(hasattr(self.bridge, "run_worker"))

    def test_22_mission_cannot_bypass_campaign_manager_to_supervisor(self) -> None:
        # Verify CampaignBridge interacts only through CampaignManager
        bridge_source = inspect.getsource(CampaignBridge)
        self.assertNotIn("supervisoradapter.submit", bridge_source.lower())
        self.assertNotIn("run_job.py", bridge_source.lower())
        self.assertNotIn("from supervisor import", bridge_source)

    def test_23_approval_gate_lifecycle(self) -> None:
        plan = self._sample_plan()
        plan["jobs"][0]["requires_approval"] = True
        self.bridge.submit_mission(plan)

        status1 = self.bridge.reconcile_mission("test-mission-01")
        self.assertEqual(status1["status"], MissionState.WAITING_APPROVAL)

        # Approve job
        self.bridge.approve_mission_job("test-mission-01", "job-a")
        self.assertEqual(self.fake_cm.jobs["job-a"]["state"], JobState.QUEUED)

    def test_24_render_mission_summary(self) -> None:
        plan = self._sample_plan()
        self.bridge.submit_mission(plan)
        summary = self.bridge.render_mission_summary("test-mission-01")
        self.assertIn("Mission test-mission-01", summary)
        self.assertIn("Campaign mission-test-mission-01", summary)


class TestRealCampaignManagerIntegration(unittest.TestCase):
    """Integration test with real CampaignManager backed by SQLite and FakeSupervisorAdapter."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="cm_int_test_")
        self.missions_db = Path(self.tmp_dir) / "missions.db"
        self.campaigns_db = Path(self.tmp_dir) / "campaigns.db"
        self.receipt_dir = Path(self.tmp_dir) / "mission_receipts"
        self.sup_receipt_dir = Path(self.tmp_dir) / "sup_receipts"
        self.workspace = Path(self.tmp_dir) / "workspace"

        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        self.sup_receipt_dir.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)

        from campaign_manager.schema import init_db as init_campaign_db
        init_campaign_db(self.campaigns_db)

        self.fake_adapter = FakeSupervisorAdapter()
        self.real_cm = CampaignManager(
            db_path=self.campaigns_db,
            adapter=self.fake_adapter,
            lease_duration_seconds=30,
        )

        self.bridge = CampaignBridge(
            db_path=self.missions_db,
            campaign_manager=self.real_cm,
            receipt_dir=self.receipt_dir,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_real_campaign_manager_complete_lifecycle(self) -> None:
        plan = {
            "mission_id": "int-mission-01",
            "title": "Integration Test Mission",
            "objective": "Verify bridge with real CampaignManager",
            "jobs": [
                {
                    "job_id": "int-job-a",
                    "title": "Job A",
                    "objective": "Create artifact A",
                    "workspace": str(self.workspace),
                    "allowed_changes": ["a.txt"],
                    "acceptance": [{"type": "file_exists", "path": "a.txt"}],
                    "dependencies": [],
                    "timeout_seconds": 30,
                    "max_attempts": 1,
                    "retry_safe": True,
                    "receipt_destination": str(self.sup_receipt_dir),
                },
                {
                    "job_id": "int-job-b",
                    "title": "Job B",
                    "objective": "Create artifact B",
                    "workspace": str(self.workspace),
                    "allowed_changes": ["b.txt"],
                    "acceptance": [{"type": "file_exists", "path": "b.txt"}],
                    "dependencies": ["int-job-a"],
                    "timeout_seconds": 30,
                    "max_attempts": 1,
                    "retry_safe": True,
                    "receipt_destination": str(self.sup_receipt_dir),
                },
            ],
        }

        # Submit mission
        sub_status = self.bridge.submit_mission(plan)
        self.assertEqual(sub_status["status"], MissionState.SUBMITTED)
        self.assertEqual(sub_status["campaign_id"], "mission-int-mission-01")

        # Configure fake supervisor adapter to PASS jobs with matching receipt identities
        self.fake_adapter.set_result(
            "mission-int-mission-01-int-job-a-1",
            SupervisorResult(
                final_status="PASS",
                reason="ACCEPTANCE_PASSED",
                receipt={"final_status": "PASS", "job_id": "mission-int-mission-01-int-job-a-1"},
                receipt_id="rcpt-a-1",
            )
        )
        self.fake_adapter.set_result(
            "mission-int-mission-01-int-job-b-1",
            SupervisorResult(
                final_status="PASS",
                reason="ACCEPTANCE_PASSED",
                receipt={"final_status": "PASS", "job_id": "mission-int-mission-01-int-job-b-1"},
                receipt_id="rcpt-b-1",
            )
        )

        # Run mission
        res = self.bridge.run_mission("int-mission-01")
        self.assertEqual(res["status"], MissionState.COMPLETED)
        self.assertEqual(res["campaign_status"], CampaignStatus.COMPLETED)

        # Verify mission receipt was written
        receipt = self.bridge.get_mission_receipt("int-mission-01")
        self.assertEqual(receipt["final_verdict"], MissionState.COMPLETED)
        self.assertEqual(receipt["campaign_id"], "mission-int-mission-01")
        self.assertEqual(len(receipt["jobs"]), 2)
        for j in receipt["jobs"]:
            self.assertEqual(j["state"], JobState.PASS)


if __name__ == "__main__":
    unittest.main()

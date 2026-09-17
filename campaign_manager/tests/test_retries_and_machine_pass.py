from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import JobState
from campaign_manager.manager import CampaignManager
from campaign_manager.models import SupervisorResult
from campaign_manager.tests.helpers import sample_work_order


class RetriesAndMachinePassTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_retries_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_pass_cannot_be_created_from_worker_text_alone(self):
        """8. PASS cannot be created from worker text alone."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Worker text claims success, but no machine receipt or receipt status is NOT PASS
        adapter.set_result(
            "prose-job",
            SupervisorResult(
                final_status="UNKNOWN",
                reason="NO_MACHINE_RECEIPT",
                receipt=None,  # No machine receipt!
                worker_prose="STATUS: PASS\nAll requirements satisfied successfully!",
            ),
        )

        spec = {
            "name": "Worker Text Test",
            "jobs": [
                {
                    "job_id": "prose-job",
                    "name": "Prose Job",
                    "work_order": sample_work_order("prose-job", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        mgr.run_campaign(cid)

        job = mgr.get_job("prose-job")
        self.assertNotEqual(job.state, JobState.PASS, "Worker prose must NEVER produce PASS")
        self.assertEqual(job.state, JobState.FAIL)

    def test_02_external_machine_failure_overrides_fabricated_worker_pass(self):
        """9. External/machine failure overrides fabricated worker PASS."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Worker text says PASS, but machine receipt says FAIL due to acceptance check failure
        machine_receipt = {
            "schema_version": "1",
            "receipt_id": "rcpt-fail-acceptance",
            "job_id": "fake-pass-job",
            "final_status": "FAIL",
            "reason": "FAIL_ACCEPTANCE",
            "acceptance_results": [{"type": "file_exact", "path": "allowed.txt", "ok": False}],
        }
        adapter.set_result(
            "fake-pass-job",
            SupervisorResult(
                final_status="FAIL",
                reason="FAIL_ACCEPTANCE",
                receipt=machine_receipt,
                receipt_id="rcpt-fail-acceptance",
                worker_prose="Everything looks great. STATUS: PASS",
            ),
        )

        spec = {
            "name": "Machine Override Test",
            "jobs": [
                {
                    "job_id": "fake-pass-job",
                    "name": "Fake Pass Job",
                    "work_order": sample_work_order("fake-pass-job", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        mgr.run_campaign(cid)

        job = mgr.get_job("fake-pass-job")
        self.assertEqual(job.state, JobState.FAIL)
        self.assertEqual(job.failure_reason, "FAIL_ACCEPTANCE")

    def test_03_bounded_retries_work(self):
        """10. Bounded retries work."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # First attempt fails, second attempt passes
        attempt_count = 0

        def dynamic_handler(work_order):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                return SupervisorResult(
                    final_status="FAIL",
                    reason="TRANSIENT_FAILURE",
                    receipt={"schema_version": "1", "job_id": "retry-job", "final_status": "FAIL", "reason": "TRANSIENT_FAILURE", "receipt_id": "r1"},
                    receipt_id="r1",
                )
            else:
                return SupervisorResult(
                    final_status="PASS",
                    reason="PASS",
                    receipt={"schema_version": "1", "job_id": "retry-job", "final_status": "PASS", "reason": "PASS", "receipt_id": "r2"},
                    receipt_id="r2",
                )

        adapter.set_result("retry-job", dynamic_handler)

        spec = {
            "name": "Retry Test",
            "jobs": [
                {
                    "job_id": "retry-job",
                    "name": "Retryable Job",
                    "work_order": sample_work_order("retry-job", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 3,
                    "retry_safe": True,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        status = mgr.run_campaign(cid)

        job = mgr.get_job("retry-job")
        self.assertEqual(job.state, JobState.PASS)
        self.assertEqual(job.attempts_used, 2)
        self.assertEqual(attempt_count, 2)
        self.assertEqual(job.last_supervisor_receipt_id, "r2")
        self.assertEqual(status["counts"][JobState.PASS], 1)

    def test_04_exhausted_retries_become_fail(self):
        """11. Exhausted retries become FAIL."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Always fails
        attempt_count = 0

        def fail_handler(work_order):
            nonlocal attempt_count
            attempt_count += 1
            return SupervisorResult(
                final_status="FAIL",
                reason="PERSISTENT_ERROR",
                receipt={"schema_version": "1", "job_id": "exhaust-job", "final_status": "FAIL", "reason": "PERSISTENT_ERROR", "receipt_id": f"rf-{attempt_count}"},
                receipt_id=f"rf-{attempt_count}",
            )

        adapter.set_result("exhaust-job", fail_handler)

        spec = {
            "name": "Exhaust Retries Test",
            "jobs": [
                {
                    "job_id": "exhaust-job",
                    "name": "Exhaust Job",
                    "work_order": sample_work_order("exhaust-job", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 2,
                    "retry_safe": True,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        status = mgr.run_campaign(cid)

        job = mgr.get_job("exhaust-job")
        self.assertEqual(job.state, JobState.FAIL)
        self.assertEqual(job.attempts_used, 2)
        self.assertEqual(attempt_count, 2)
        self.assertEqual(job.failure_reason, "PERSISTENT_ERROR")
        self.assertEqual(status["counts"][JobState.FAIL], 1)


if __name__ == "__main__":
    unittest.main()

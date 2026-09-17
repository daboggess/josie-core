from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import CampaignStatus, JobState
from campaign_manager.manager import CampaignManager
from campaign_manager.models import SupervisorResult
from campaign_manager.tests.helpers import sample_campaign_spec, sample_work_order


class DependencyBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_dep_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_dependencies_prevent_early_dispatch(self):
        """3. Dependencies prevent early dispatch."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Dep Order Test",
            "jobs": [
                {
                    "job_id": "job-1",
                    "name": "First Job",
                    "work_order": sample_work_order("job-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-2",
                    "name": "Second Job",
                    "work_order": sample_work_order("job-2", self.workspace, self.receipts),
                    "dependencies": ["job-1"],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
            ],
        }
        cid = mgr.create_campaign(spec)

        # Claiming next runnable job must return job-1, NEVER job-2
        claimed1 = mgr.claim_next_job(cid)
        self.assertIsNotNone(claimed1)
        self.assertEqual(claimed1.job_id, "job-1")

        # While job-1 is RUNNING (not yet PASS), job-2 cannot be claimed
        claimed_none = mgr.claim_next_job(cid)
        self.assertIsNone(claimed_none, "job-2 must not be claimed while job-1 is RUNNING")

        # Dispatch job-1 to completion (PASS)
        mgr.dispatch_job(claimed1)
        self.assertEqual(mgr.get_job("job-1").state, JobState.PASS)

        # Now job-2 should be claimable
        claimed2 = mgr.claim_next_job(cid)
        self.assertIsNotNone(claimed2)
        self.assertEqual(claimed2.job_id, "job-2")

    def test_02_dependency_failure_blocks_dependent_work(self):
        """5. Dependency failure blocks dependent work."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Fail job-1 with machine FAIL receipt
        fail_receipt = {
            "schema_version": "1",
            "receipt_id": "fail-rcpt-1",
            "job_id": "job-1",
            "final_status": "FAIL",
            "reason": "FAIL_ACCEPTANCE",
        }
        adapter.set_result(
            "job-1",
            SupervisorResult(
                final_status="FAIL",
                reason="FAIL_ACCEPTANCE",
                receipt=fail_receipt,
                receipt_id="fail-rcpt-1",
            ),
        )

        spec = {
            "name": "Dep Failure Test",
            "jobs": [
                {
                    "job_id": "job-1",
                    "name": "Failing Job",
                    "work_order": sample_work_order("job-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-2",
                    "name": "Dependent Job",
                    "work_order": sample_work_order("job-2", self.workspace, self.receipts),
                    "dependencies": ["job-1"],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
            ],
        }
        cid = mgr.create_campaign(spec)

        status = mgr.run_campaign(cid)

        job1 = mgr.get_job("job-1")
        job2 = mgr.get_job("job-2")

        self.assertEqual(job1.state, JobState.FAIL)
        self.assertEqual(job2.state, JobState.BLOCKED)
        self.assertIn("job-1", job2.failure_reason)
        self.assertEqual(status["counts"][JobState.BLOCKED], 1)
        self.assertEqual(status["counts"][JobState.FAIL], 1)

    def test_03_independent_work_continues_when_another_branch_blocked(self):
        """4. Independent work continues when another branch is blocked."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Branch A: job-a1 (fails) -> job-a2 (should get blocked)
        # Branch B: job-b1 (independent, passes) -> job-b2 (independent, passes)
        fail_receipt = {
            "schema_version": "1",
            "receipt_id": "fail-a1",
            "job_id": "job-a1",
            "final_status": "FAIL",
            "reason": "FAIL_COMPILE",
        }
        adapter.set_result(
            "job-a1",
            SupervisorResult(
                final_status="FAIL",
                reason="FAIL_COMPILE",
                receipt=fail_receipt,
                receipt_id="fail-a1",
            ),
        )

        spec = {
            "name": "Branch Independence Test",
            "jobs": [
                {
                    "job_id": "job-a1",
                    "name": "Branch A Root (Fails)",
                    "work_order": sample_work_order("job-a1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-a2",
                    "name": "Branch A Child (Should Block)",
                    "work_order": sample_work_order("job-a2", self.workspace, self.receipts),
                    "dependencies": ["job-a1"],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-b1",
                    "name": "Branch B Root (Passes)",
                    "work_order": sample_work_order("job-b1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-b2",
                    "name": "Branch B Child (Passes)",
                    "work_order": sample_work_order("job-b2", self.workspace, self.receipts),
                    "dependencies": ["job-b1"],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
            ],
        }
        cid = mgr.create_campaign(spec)
        status = mgr.run_campaign(cid)

        job_a1 = mgr.get_job("job-a1")
        job_a2 = mgr.get_job("job-a2")
        job_b1 = mgr.get_job("job-b1")
        job_b2 = mgr.get_job("job-b2")

        self.assertEqual(job_a1.state, JobState.FAIL)
        self.assertEqual(job_a2.state, JobState.BLOCKED)
        self.assertEqual(job_b1.state, JobState.PASS)
        self.assertEqual(job_b2.state, JobState.PASS)

        self.assertEqual(status["counts"][JobState.PASS], 2)
        self.assertEqual(status["counts"][JobState.FAIL], 1)
        self.assertEqual(status["counts"][JobState.BLOCKED], 1)


if __name__ == "__main__":
    unittest.main()

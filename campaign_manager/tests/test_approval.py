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


class ApprovalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_app_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_waiting_approval_does_not_stop_unrelated_runnable_jobs(self):
        """17. WAITING_APPROVAL does not stop unrelated runnable jobs."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Job 1 requires approval (enters WAITING_APPROVAL)
        # Job 2 depends on Job 1 (must stay queued)
        # Job 3 is independent (must run and pass)
        adapter.set_result(
            "job-needs-approval",
            SupervisorResult(
                final_status="WAITING_APPROVAL",
                reason="HOST_MUTATION_APPROVAL_REQUIRED",
            ),
        )

        spec = {
            "name": "Approval Independence Campaign",
            "jobs": [
                {
                    "job_id": "job-needs-approval",
                    "name": "Needs Approval",
                    "work_order": sample_work_order("job-needs-approval", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-dependent-on-approval",
                    "name": "Dependent on Approval",
                    "work_order": sample_work_order("job-dependent-on-approval", self.workspace, self.receipts),
                    "dependencies": ["job-needs-approval"],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-independent",
                    "name": "Independent Job",
                    "work_order": sample_work_order("job-independent", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
            ],
        }
        cid = mgr.create_campaign(spec)
        status = mgr.run_campaign(cid)

        job1 = mgr.get_job("job-needs-approval")
        job2 = mgr.get_job("job-dependent-on-approval")
        job3 = mgr.get_job("job-independent")

        self.assertEqual(job1.state, JobState.WAITING_APPROVAL)
        self.assertEqual(job2.state, JobState.QUEUED)
        self.assertEqual(job3.state, JobState.PASS)

        self.assertEqual(status["counts"][JobState.PASS], 1)
        self.assertEqual(status["counts"][JobState.WAITING_APPROVAL], 1)
        self.assertEqual(status["counts"][JobState.QUEUED], 1)

    def test_02_approving_job_allows_it_to_run(self):
        """Approve job transitions from WAITING_APPROVAL to QUEUED and then runs to completion."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Manual Approval Test",
            "jobs": [
                {
                    "job_id": "gated-job",
                    "name": "Gated Job",
                    "work_order": sample_work_order("gated-job", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                    "initial_state": JobState.WAITING_APPROVAL,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        self.assertEqual(mgr.get_job("gated-job").state, JobState.WAITING_APPROVAL)

        # Running campaign while in WAITING_APPROVAL does not run it
        mgr.run_campaign(cid)
        self.assertEqual(mgr.get_job("gated-job").state, JobState.WAITING_APPROVAL)

        # Explicit operator approval
        mgr.approve_job("gated-job")
        self.assertEqual(mgr.get_job("gated-job").state, JobState.QUEUED)

        # Now running the campaign drains the approved job to PASS
        mgr.run_campaign(cid)
        self.assertEqual(mgr.get_job("gated-job").state, JobState.PASS)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import CampaignStatus, JobState
from campaign_manager.db import get_connection
from campaign_manager.manager import CampaignManager
from campaign_manager.models import SupervisorResult
from campaign_manager.tests.helpers import sample_work_order


class CrashRecoveryFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_crash_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_deterministic_crash_fixture_with_pass_receipt(self):
        """CRASH TEST FIXTURE (Durable Evidence Recovery):
        
        1. create a campaign with at least three jobs;
        2. establish at least one dependency;
        3. claim/start one job;
        4. simulate process death/stale lease before Campaign Manager records completion;
        5. reopen the database in a fresh manager instance;
        6. run reconciliation;
        7. prove the correct state is recovered from durable evidence or safe retry/block policy;
        8. continue processing any independent runnable work.
        This test must require no human intervention.
        """
        adapter1 = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter1, runner_id="runner-crashed-pid-101")

        # 1. create a campaign with at least three jobs;
        # 2. establish at least one dependency (job-2 depends on job-1); job-3 is independent.
        spec = {
            "name": "Crash Recovery Campaign",
            "jobs": [
                {
                    "job_id": "job-1",
                    "name": "Job 1 (Crashes mid-run)",
                    "work_order": sample_work_order("job-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 2,
                    "retry_safe": True,
                },
                {
                    "job_id": "job-2",
                    "name": "Job 2 (Depends on Job 1)",
                    "work_order": sample_work_order("job-2", self.workspace, self.receipts),
                    "dependencies": ["job-1"],
                    "max_attempts": 2,
                    "retry_safe": True,
                },
                {
                    "job_id": "job-3",
                    "name": "Job 3 (Independent)",
                    "work_order": sample_work_order("job-3", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 2,
                    "retry_safe": True,
                },
            ],
        }
        cid = mgr1.create_campaign(spec)

        # 3. claim/start one job (job-1)
        job1_claimed = mgr1.claim_next_job(cid)
        self.assertIsNotNone(job1_claimed)
        self.assertEqual(job1_claimed.job_id, "job-1")
        self.assertEqual(job1_claimed.state, JobState.RUNNING)
        self.assertEqual(job1_claimed.runner_id, "runner-crashed-pid-101")

        # 4. simulate process death/stale lease before Campaign Manager records completion.
        # Supervisor finished and wrote a durable PASS receipt, but manager died before writing to DB:
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = 'job-1'")
        conn.execute("UPDATE campaigns SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE campaign_id = ?", (cid,))
        conn.commit()
        conn.close()

        job1_receipt = {
            "schema_version": "1",
            "receipt_id": "receipt-job-1-survived",
            "job_id": job1_claimed.current_supervisor_job_id,
            "final_status": "PASS",
            "reason": "PASS",
        }
        rcpt_path = self.receipts / "receipt-job-1-survived.json"
        rcpt_path.write_text(json.dumps(job1_receipt), encoding="utf-8")

        # Drop mgr1 reference to simulate process death
        del mgr1

        # 5. reopen the database in a fresh manager instance
        adapter2 = FakeSupervisorAdapter()
        # Wire adapter2 to find the written receipt file on disk
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter2, runner_id="runner-fresh-pid-202")

        # 6. run reconciliation
        reconciled = mgr2.reconcile(cid)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["job_id"], "job-1")
        self.assertEqual(reconciled[0]["state_to"], JobState.PASS)

        # 7. prove the correct state is recovered from durable evidence
        recovered_job1 = mgr2.get_job("job-1")
        self.assertEqual(recovered_job1.state, JobState.PASS)
        self.assertEqual(recovered_job1.last_supervisor_receipt_id, "receipt-job-1-survived")
        self.assertIsNone(recovered_job1.runner_id)

        # 8. continue processing any independent runnable work
        # Now running the drain loop should execute job-2 (now unblocked) and job-3 (independent)
        status = mgr2.run_campaign(cid)

        job1_final = mgr2.get_job("job-1")
        job2_final = mgr2.get_job("job-2")
        job3_final = mgr2.get_job("job-3")

        self.assertEqual(job1_final.state, JobState.PASS)
        self.assertEqual(job2_final.state, JobState.PASS)
        self.assertEqual(job3_final.state, JobState.PASS)

        self.assertEqual(status["status"], CampaignStatus.COMPLETED)
        self.assertEqual(status["counts"][JobState.PASS], 3)
        self.assertEqual(status["counts"][JobState.RUNNING], 0)
        self.assertEqual(status["counts"][JobState.QUEUED], 0)
        self.assertEqual(status["counts"][JobState.BLOCKED], 0)

    def test_deterministic_crash_fixture_with_uncertain_execution_retry_policy(self):
        """CRASH TEST FIXTURE (Uncertain Execution & Safe Policy Recovery):
        
        Simulates crash where NO receipt was written:
        - Job 1 is retry_safe=True -> reconciles to RETRY, then runs again and passes.
        - Job 2 depends on Job 1 -> unblocks and passes.
        - Job 3 is independent -> passes.
        """
        adapter1 = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter1, runner_id="runner-crashed-pid-303")

        spec = {
            "name": "Crash Policy Campaign",
            "jobs": [
                {
                    "job_id": "job-1",
                    "name": "Job 1 (Uncertain crash)",
                    "work_order": sample_work_order("job-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 2,
                    "retry_safe": True,
                },
                {
                    "job_id": "job-2",
                    "name": "Job 2 (Dependent on Job 1)",
                    "work_order": sample_work_order("job-2", self.workspace, self.receipts),
                    "dependencies": ["job-1"],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
                {
                    "job_id": "job-3",
                    "name": "Job 3 (Independent)",
                    "work_order": sample_work_order("job-3", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                },
            ],
        }
        cid = mgr1.create_campaign(spec)
        claimed = mgr1.claim_next_job(cid)
        self.assertEqual(claimed.job_id, "job-1")
        self.assertEqual(claimed.attempts_used, 1)

        # Simulate crash without writing receipt, and lease expiring
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = 'job-1'")
        conn.execute("UPDATE campaigns SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE campaign_id = ?", (cid,))
        conn.commit()
        conn.close()

        del mgr1

        adapter2 = FakeSupervisorAdapter()
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter2, runner_id="runner-fresh-pid-404")

        # Reconciliation: retry_safe=True and attempts_used=1 < max_attempts=2 -> RETRY
        reconciled = mgr2.reconcile(cid)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["job_id"], "job-1")
        self.assertEqual(reconciled[0]["state_to"], JobState.RETRY)

        job1_rec = mgr2.get_job("job-1")
        self.assertEqual(job1_rec.state, JobState.RETRY)

        # Drain loop: runs job-1 (attempt 2), job-2, job-3 to completion
        status = mgr2.run_campaign(cid)
        self.assertEqual(status["status"], CampaignStatus.COMPLETED)
        self.assertEqual(status["counts"][JobState.PASS], 3)
        self.assertEqual(mgr2.get_job("job-1").attempts_used, 2)


if __name__ == "__main__":
    unittest.main()

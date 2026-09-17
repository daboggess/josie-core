from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import JobState
from campaign_manager.db import get_connection, now_utc
from campaign_manager.manager import CampaignManager
from campaign_manager.tests.helpers import sample_work_order


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_rec_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_stale_running_with_valid_pass_receipt_reconciles_to_pass(self):
        """12. Stale RUNNING + valid PASS receipt reconciles to PASS."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Reconcile Pass Test",
            "jobs": [
                {
                    "job_id": "job-reconcile-pass",
                    "name": "Reconcile Pass",
                    "work_order": sample_work_order("job-reconcile-pass", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 2,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr.create_campaign(spec)

        # Claim the job to move to RUNNING
        job = mgr.claim_next_job(cid)
        self.assertEqual(job.state, JobState.RUNNING)

        # Simulate that supervisor finished and wrote receipt to disk, but manager crashed and lease expired
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = ?", (job.job_id,))
        conn.commit()
        conn.close()

        rcpt = {
            "schema_version": "1",
            "receipt_id": "receipt-pass-123",
            "job_id": job.current_supervisor_job_id,
            "final_status": "PASS",
            "reason": "PASS",
        }
        rcpt_file = self.receipts / f"{job.current_supervisor_job_id}.json"
        rcpt_file.write_text(json.dumps(rcpt), encoding="utf-8")
        adapter.store_receipt(job.current_supervisor_job_id, rcpt, rcpt_file)

        # Fresh CampaignManager instance runs reconciliation
        mgr_fresh = CampaignManager(db_path=self.db_path, adapter=adapter)
        reconciled = mgr_fresh.reconcile(cid)

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["job_id"], "job-reconcile-pass")
        self.assertEqual(reconciled[0]["state_to"], JobState.PASS)

        persisted = mgr_fresh.get_job("job-reconcile-pass")
        self.assertEqual(persisted.state, JobState.PASS)
        self.assertEqual(persisted.last_supervisor_receipt_id, "receipt-pass-123")
        self.assertIsNone(persisted.runner_id)

    def test_02_stale_running_unknown_result_retry_safe_true_becomes_retry(self):
        """13. Stale RUNNING + unknown result + retry_safe=true becomes RETRY when attempts remain."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Reconcile Retry Test",
            "jobs": [
                {
                    "job_id": "job-reconcile-retry",
                    "name": "Reconcile Retry",
                    "work_order": sample_work_order("job-reconcile-retry", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 3,
                    "retry_safe": True,
                }
            ],
        }
        cid = mgr.create_campaign(spec)

        # Claim the job (attempts_used becomes 1)
        job = mgr.claim_next_job(cid)
        self.assertEqual(job.state, JobState.RUNNING)
        self.assertEqual(job.attempts_used, 1)

        # Simulate manager crash and lease expiry without supervisor writing anything
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = ?", (job.job_id,))
        conn.execute("UPDATE campaigns SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE campaign_id = ?", (cid,))
        conn.commit()
        conn.close()

        # No receipt written (simulating sudden crash before supervisor wrote anything)
        mgr_fresh = CampaignManager(db_path=self.db_path, adapter=adapter)
        reconciled = mgr_fresh.reconcile(cid)

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["job_id"], "job-reconcile-retry")
        self.assertEqual(reconciled[0]["state_to"], JobState.RETRY)
        self.assertEqual(reconciled[0]["reason"], "RETRY_AFTER_CRASH")

        persisted = mgr_fresh.get_job("job-reconcile-retry")
        self.assertEqual(persisted.state, JobState.RETRY)
        self.assertEqual(persisted.failure_reason, "RETRY_AFTER_CRASH")
        self.assertIsNone(persisted.runner_id)
        # Should be claimable again!
        reclaimed = mgr_fresh.claim_next_job(cid)
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed.job_id, "job-reconcile-retry")
        self.assertEqual(reclaimed.attempts_used, 2)

    def test_03_stale_running_unknown_result_retry_safe_false_becomes_blocked(self):
        """14. Stale RUNNING + unknown result + retry_safe=false becomes BLOCKED with UNCERTAIN_EXECUTION."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Reconcile Blocked Test",
            "jobs": [
                {
                    "job_id": "job-reconcile-blocked",
                    "name": "Reconcile Blocked",
                    "work_order": sample_work_order("job-reconcile-blocked", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 3,
                    "retry_safe": False,  # NOT safe to retry with uncertain execution!
                }
            ],
        }
        cid = mgr.create_campaign(spec)

        job = mgr.claim_next_job(cid)
        self.assertEqual(job.state, JobState.RUNNING)

        # Simulate manager crash and lease expiry
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = ?", (job.job_id,))
        conn.commit()
        conn.close()

        # Fresh manager instance reconciles without any receipt
        mgr_fresh = CampaignManager(db_path=self.db_path, adapter=adapter)
        reconciled = mgr_fresh.reconcile(cid)

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["job_id"], "job-reconcile-blocked")
        self.assertEqual(reconciled[0]["state_to"], JobState.BLOCKED)
        self.assertEqual(reconciled[0]["reason"], "UNCERTAIN_EXECUTION")

        persisted = mgr_fresh.get_job("job-reconcile-blocked")
        self.assertEqual(persisted.state, JobState.BLOCKED)
        self.assertEqual(persisted.failure_reason, "UNCERTAIN_EXECUTION")
        self.assertIsNone(persisted.runner_id)


if __name__ == "__main__":
    unittest.main()

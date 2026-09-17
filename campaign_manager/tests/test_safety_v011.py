from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import CampaignStatus, DEFAULT_LEASE_GRACE_SECONDS, JobState
from campaign_manager.db import get_connection, now_utc
from campaign_manager.errors import CampaignAlreadyRunningError
from campaign_manager.manager import CampaignManager
from campaign_manager.tests.helpers import sample_work_order


class SafetyV011Tests(unittest.TestCase):
    """Dedicated regression suite for v0.1.1 safety hardening:
    - Defect 1: Stale lease detection (unexpired untouched, expired reconciled, malformed fail-conservative)
    - Defect 2: Globally sequential per campaign (campaign lease ownership, concurrency block, safe takeover)
    - Defect 3: Exact execution attempt identity (durable attempt ID, exact receipt matching, restart preservation)
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_safety_v011_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_simple_campaign(self, mgr: CampaignManager, name: str, timeout_seconds: int = 120, retry_safe: bool = True, max_attempts: int = 2) -> str:
        spec = {
            "name": name,
            "jobs": [
                {
                    "job_id": "job-safety-1",
                    "name": "Safety Test Job",
                    "work_order": sample_work_order("job-safety-1", self.workspace, self.receipts, timeout_seconds=timeout_seconds),
                    "dependencies": [],
                    "max_attempts": max_attempts,
                    "retry_safe": retry_safe,
                }
            ],
        }
        return mgr.create_campaign(spec)

    def test_01_active_unexpired_running_job_is_untouched_by_reconcile(self):
        """DEFECT 1: Automatic reconciliation must never touch an active unexpired RUNNING job."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-active-1")
        cid = self._create_simple_campaign(mgr, "Active Unexpired Job Test")

        # Claim the job: it gets a lease in the future
        job = mgr.claim_next_job(cid)
        self.assertIsNotNone(job)
        self.assertEqual(job.state, JobState.RUNNING)
        self.assertIsNotNone(job.lease_expires_at)

        # Another manager instance (or crash recovery agent) invokes reconcile()
        mgr_observer = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-observer")
        reconciled = mgr_observer.reconcile(cid)

        # Reconcile MUST NOT touch the job because its lease is active
        self.assertEqual(len(reconciled), 0)

        persisted = mgr_observer.get_job("job-safety-1")
        self.assertEqual(persisted.state, JobState.RUNNING)
        self.assertEqual(persisted.runner_id, "runner-active-1")
        self.assertEqual(persisted.lease_expires_at, job.lease_expires_at)

    def test_02_expired_running_job_is_reconciled(self):
        """DEFECT 1: A RUNNING job whose lease has expired is reconciled."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-expired-1")
        cid = self._create_simple_campaign(mgr, "Expired Job Test")

        job = mgr.claim_next_job(cid)
        self.assertEqual(job.state, JobState.RUNNING)

        # Simulate lease expiry
        past_time = "2020-01-01T00:00:00+00:00"
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = ? WHERE job_id = ?", (past_time, job.job_id))
        conn.commit()
        conn.close()

        # Observer runs reconcile
        mgr_observer = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-observer")
        reconciled = mgr_observer.reconcile(cid)

        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["job_id"], "job-safety-1")
        self.assertEqual(reconciled[0]["state_to"], JobState.RETRY)

        persisted = mgr_observer.get_job("job-safety-1")
        self.assertEqual(persisted.state, JobState.RETRY)
        self.assertIsNone(persisted.runner_id)

    def test_03_missing_or_malformed_lease_fails_conservatively(self):
        """DEFECT 1: Missing or unparseable lease_expires_at fails conservatively (leaves job RUNNING)."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-malformed-1")
        cid = self._create_simple_campaign(mgr, "Malformed Lease Test")

        job = mgr.claim_next_job(cid)
        self.assertEqual(job.state, JobState.RUNNING)

        # Case A: NULL lease_expires_at
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = NULL WHERE job_id = ?", (job.job_id,))
        conn.commit()
        conn.close()

        mgr_observer = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-observer")
        reconciled_null = mgr_observer.reconcile(cid)
        self.assertEqual(len(reconciled_null), 0, "NULL lease must be treated conservatively as unexpired")
        self.assertEqual(mgr_observer.get_job("job-safety-1").state, JobState.RUNNING)

        # Case B: Malformed string lease_expires_at
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = 'not-a-valid-iso-timestamp' WHERE job_id = ?", (job.job_id,))
        conn.commit()
        conn.close()

        reconciled_malformed = mgr_observer.reconcile(cid)
        self.assertEqual(len(reconciled_malformed), 0, "Malformed lease must be treated conservatively as unexpired")
        self.assertEqual(mgr_observer.get_job("job-safety-1").state, JobState.RUNNING)

    def test_04_campaign_lease_blocks_second_runner(self):
        """DEFECT 2: Campaign lease ownership blocks a second runner from claiming/running concurrently."""
        adapter = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-first")
        cid = self._create_simple_campaign(mgr1, "Campaign Lease Concurrency Test")

        # First runner claims the job, acquiring the campaign lease
        job = mgr1.claim_next_job(cid)
        self.assertIsNotNone(job)

        # Campaign record reflects runner-first lease
        camp = mgr1.get_campaign(cid)
        self.assertEqual(camp.runner_id, "runner-first")
        self.assertIsNotNone(camp.lease_expires_at)

        # Second runner attempts to claim in the same campaign
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-second")
        with self.assertRaises(CampaignAlreadyRunningError):
            mgr2.claim_next_job(cid)

        # Second runner attempts to run the campaign
        with self.assertRaises(CampaignAlreadyRunningError):
            mgr2.run_campaign(cid)

    def test_05_safe_campaign_lease_takeover_after_expiry(self):
        """DEFECT 2: After a runner's campaign lease expires, another runner safely takes over."""
        adapter = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-first")
        cid = self._create_simple_campaign(mgr1, "Campaign Lease Takeover Test")

        # First runner acquires campaign lease
        mgr1.acquire_campaign_lease(cid, lease_seconds=10)
        camp = mgr1.get_campaign(cid)
        self.assertEqual(camp.runner_id, "runner-first")

        # Second runner cannot acquire yet
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-second")
        with self.assertRaises(CampaignAlreadyRunningError):
            mgr2.acquire_campaign_lease(cid, lease_seconds=60)

        # Simulate campaign lease expiry
        past_time = "2020-01-01T00:00:00+00:00"
        conn = get_connection(self.db_path)
        conn.execute("UPDATE campaigns SET lease_expires_at = ? WHERE campaign_id = ?", (past_time, cid))
        conn.commit()
        conn.close()

        # Second runner can now acquire campaign lease successfully
        mgr2.acquire_campaign_lease(cid, lease_seconds=60)
        camp_after = mgr2.get_campaign(cid)
        self.assertEqual(camp_after.runner_id, "runner-second")

    def test_06_job_lease_derived_from_work_order_timeout_plus_grace(self):
        """DEFECT 2: Execution lease duration is derived from timeout_seconds + DEFAULT_LEASE_GRACE_SECONDS."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-timeout-test")
        timeout_seconds = 180
        cid = self._create_simple_campaign(mgr, "Timeout Lease Derivation Test", timeout_seconds=timeout_seconds)

        job = mgr.claim_next_job(cid)

        self.assertIsNotNone(job.claimed_at)
        self.assertIsNotNone(job.lease_expires_at)

        claimed_dt = datetime.fromisoformat(job.claimed_at)
        lease_exp_dt = datetime.fromisoformat(job.lease_expires_at)
        duration = (lease_exp_dt - claimed_dt).total_seconds()

        expected_duration = timeout_seconds + DEFAULT_LEASE_GRACE_SECONDS
        self.assertAlmostEqual(duration, expected_duration, delta=2.0)

    def test_07_exact_attempt_receipt_correlation(self):
        """DEFECT 3: Receipt lookup matches the exact attempt identity and ignores older attempt receipts."""
        adapter = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-attempt-1")
        cid = self._create_simple_campaign(mgr1, "Exact Attempt Identity Test", max_attempts=3, retry_safe=True)

        # Attempt 1: claimed
        job_a1 = mgr1.claim_next_job(cid)
        self.assertEqual(job_a1.attempts_used, 1)
        a1_sup_job_id = job_a1.current_supervisor_job_id
        self.assertTrue(a1_sup_job_id.startswith("job-safety-1--a1--"))

        # Simulate attempt 1 crashing without manager recording, but writing a failure receipt
        a1_receipt = {
            "schema_version": "1",
            "receipt_id": "receipt-attempt-1-fail",
            "job_id": a1_sup_job_id,
            "final_status": "FAIL",
            "reason": "FLAKY_NETWORK",
        }
        rcpt1_file = self.receipts / f"{a1_sup_job_id}.json"
        rcpt1_file.write_text(json.dumps(a1_receipt), encoding="utf-8")
        adapter.store_receipt(a1_sup_job_id, a1_receipt, rcpt1_file)

        # Expire lease to trigger reconciliation of attempt 1
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = 'job-safety-1'")
        conn.execute("UPDATE campaigns SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE campaign_id = ?", (cid,))
        conn.commit()
        conn.close()

        # Reconcile attempt 1 -> records FAIL from receipt, transitions to RETRY since retry_safe=True
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-attempt-2")
        reconciled = mgr2.reconcile(cid)
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["state_to"], JobState.RETRY)

        attempts = mgr2.get_attempts("job-safety-1")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, JobState.FAIL)
        self.assertEqual(attempts[0].supervisor_receipt_id, "receipt-attempt-1-fail")

        # Attempt 2: claimed
        job_a2 = mgr2.claim_next_job(cid)
        self.assertEqual(job_a2.attempts_used, 2)
        a2_sup_job_id = job_a2.current_supervisor_job_id
        self.assertTrue(a2_sup_job_id.startswith("job-safety-1--a2--"))
        self.assertNotEqual(a1_sup_job_id, a2_sup_job_id)

        # Now simulate attempt 2 dying without writing any receipt, and lease expiring
        conn = get_connection(self.db_path)
        conn.execute("UPDATE jobs SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE job_id = 'job-safety-1'")
        conn.execute("UPDATE campaigns SET lease_expires_at = '2020-01-01T00:00:00+00:00' WHERE campaign_id = ?", (cid,))
        conn.commit()
        conn.close()

        # Reconcile attempt 2:
        # It MUST NOT match attempt 1's receipt file ("receipt-attempt-1-fail"), even though both share the base job_id!
        # Because no receipt exists for a2_sup_job_id, attempt 2 reconciles as RETRY_AFTER_CRASH (unknown result)
        mgr3 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-attempt-3")
        reconciled2 = mgr3.reconcile(cid)
        self.assertEqual(len(reconciled2), 1)
        self.assertEqual(reconciled2[0]["state_to"], JobState.RETRY)
        self.assertEqual(reconciled2[0]["reason"], "RETRY_AFTER_CRASH")

        attempts_after = mgr3.get_attempts("job-safety-1")
        self.assertEqual(len(attempts_after), 2)
        self.assertIsNone(attempts_after[1].supervisor_receipt_id, "Attempt 2 must NOT borrow Attempt 1 receipt")

    def test_08_in_flight_execution_identity_preserved_across_restarts(self):
        """DEFECT 3: In-flight execution identity is preserved across manager restarts without re-generation."""
        adapter = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-in-flight-1")
        cid = self._create_simple_campaign(mgr1, "Preserve Identity Across Restarts")

        job = mgr1.claim_next_job(cid)
        attempt_id_orig = job.current_attempt_id
        supervisor_job_id_orig = job.current_supervisor_job_id

        self.assertIsNotNone(attempt_id_orig)
        self.assertIsNotNone(supervisor_job_id_orig)

        # Simulate manager crash/restart without touching the DB
        del mgr1
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-restart-2")
        job_reloaded = mgr2.get_job("job-safety-1")

        self.assertEqual(job_reloaded.current_attempt_id, attempt_id_orig)
        self.assertEqual(job_reloaded.current_supervisor_job_id, supervisor_job_id_orig)

        # Attempts table confirms in-flight record
        attempts = mgr2.get_attempts("job-safety-1")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].attempt_id, attempt_id_orig)
        self.assertEqual(attempts[0].supervisor_job_id, supervisor_job_id_orig)
        self.assertEqual(attempts[0].status, JobState.RUNNING)


if __name__ == "__main__":
    unittest.main()

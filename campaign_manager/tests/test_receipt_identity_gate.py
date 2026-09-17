from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter, RealSupervisorAdapter
from campaign_manager.constants import JobState
from campaign_manager.manager import CampaignManager
from campaign_manager.models import SupervisorResult
from campaign_manager.tests.helpers import sample_work_order


class ReceiptIdentityGateTests(unittest.TestCase):
    """Live-dispatch evidence gate tests verifying that a synchronous Supervisor result
    may produce Campaign Manager PASS ONLY when:
    1. result.final_status == "PASS"
    2. result.receipt is a dict
    3. result.receipt.get("final_status") == "PASS"
    4. result.receipt.get("job_id") == job.current_supervisor_job_id

    And if receipt job_id is missing or does not match:
    - NEVER mark PASS
    - set durable failure reason RECEIPT_IDENTITY_MISMATCH
    - preserve receipt metadata for diagnosis
    - follow normal bounded retry policy if retry_safe and attempts remain
    - otherwise FAIL
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_receipt_gate_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_correct_execution_specific_receipt_id_passes(self):
        """1. Correct execution-specific receipt ID -> PASS."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Correct Receipt ID Test",
            "jobs": [
                {
                    "job_id": "job-correct-1",
                    "name": "Job with Correct Receipt ID",
                    "work_order": sample_work_order("job-correct-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        job = mgr.claim_next_job(cid)
        self.assertIsNotNone(job)
        self.assertTrue(job.current_supervisor_job_id.startswith("job-correct-1--a1--"))

        # Supervisor result with exact execution-specific job_id matching current_supervisor_job_id
        exact_sup_id = job.current_supervisor_job_id
        adapter.set_result(
            exact_sup_id,
            SupervisorResult(
                final_status="PASS",
                reason="PASS",
                receipt={
                    "schema_version": "1",
                    "receipt_id": "rcpt-exact-pass-1",
                    "job_id": exact_sup_id,
                    "final_status": "PASS",
                    "reason": "PASS",
                },
                receipt_id="rcpt-exact-pass-1",
            ),
        )

        mgr.dispatch_job(job)

        updated_job = mgr.get_job("job-correct-1")
        self.assertEqual(updated_job.state, JobState.PASS)
        self.assertIsNone(updated_job.failure_reason)
        self.assertEqual(updated_job.last_supervisor_receipt_id, "rcpt-exact-pass-1")

        attempts = mgr.get_attempts("job-correct-1")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, JobState.PASS)
        self.assertEqual(attempts[0].supervisor_receipt_id, "rcpt-exact-pass-1")

    def test_02_wrong_receipt_job_id_never_pass(self):
        """2. Wrong receipt job_id -> never PASS, set RECEIPT_IDENTITY_MISMATCH, FAIL when not retry_safe."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Wrong Receipt ID Test",
            "jobs": [
                {
                    "job_id": "job-wrong-1",
                    "name": "Job with Wrong Receipt ID",
                    "work_order": sample_work_order("job-wrong-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        job = mgr.claim_next_job(cid)
        self.assertIsNotNone(job)

        # Worker / supervisor claims PASS, but receipt has a DIFFERENT job_id
        adapter.set_result(
            job.current_supervisor_job_id,
            SupervisorResult(
                final_status="PASS",
                reason="PASS",
                receipt={
                    "schema_version": "1",
                    "receipt_id": "rcpt-wrong-id-999",
                    "job_id": "completely-wrong-execution-id",
                    "final_status": "PASS",
                    "reason": "PASS",
                },
                receipt_id="rcpt-wrong-id-999",
                receipt_path="/receipts/rcpt-wrong-id-999.json",
            ),
        )

        mgr.dispatch_job(job)

        updated_job = mgr.get_job("job-wrong-1")
        self.assertNotEqual(updated_job.state, JobState.PASS, "Must NEVER mark PASS on receipt identity mismatch")
        self.assertEqual(updated_job.state, JobState.FAIL)
        self.assertEqual(updated_job.failure_reason, "RECEIPT_IDENTITY_MISMATCH")
        # Metadata preserved for diagnosis
        self.assertEqual(updated_job.last_supervisor_receipt_id, "rcpt-wrong-id-999")

        attempts = mgr.get_attempts("job-wrong-1")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, JobState.FAIL)
        self.assertEqual(attempts[0].failure_reason, "RECEIPT_IDENTITY_MISMATCH")
        self.assertEqual(attempts[0].supervisor_receipt_id, "rcpt-wrong-id-999")

    def test_03_missing_receipt_job_id_never_pass(self):
        """3. Missing receipt job_id -> never PASS, set RECEIPT_IDENTITY_MISMATCH, preserve metadata."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Missing Receipt ID Test",
            "jobs": [
                {
                    "job_id": "job-missing-id-1",
                    "name": "Job with Missing Receipt ID",
                    "work_order": sample_work_order("job-missing-id-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        job = mgr.claim_next_job(cid)
        self.assertIsNotNone(job)

        # Receipt completely lacks "job_id"
        adapter.set_result(
            job.current_supervisor_job_id,
            SupervisorResult(
                final_status="PASS",
                reason="PASS",
                receipt={
                    "schema_version": "1",
                    "receipt_id": "rcpt-no-job-id",
                    "final_status": "PASS",
                    "reason": "PASS",
                },
                receipt_id="rcpt-no-job-id",
                receipt_path="/receipts/rcpt-no-job-id.json",
            ),
        )

        mgr.dispatch_job(job)

        updated_job = mgr.get_job("job-missing-id-1")
        self.assertNotEqual(updated_job.state, JobState.PASS, "Must NEVER mark PASS when receipt job_id is missing")
        self.assertEqual(updated_job.state, JobState.FAIL)
        self.assertEqual(updated_job.failure_reason, "RECEIPT_IDENTITY_MISMATCH")
        self.assertEqual(updated_job.last_supervisor_receipt_id, "rcpt-no-job-id")

        attempts = mgr.get_attempts("job-missing-id-1")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, JobState.FAIL)
        self.assertEqual(attempts[0].failure_reason, "RECEIPT_IDENTITY_MISMATCH")
        self.assertEqual(attempts[0].supervisor_receipt_id, "rcpt-no-job-id")

    def test_04_retry_safe_mismatch_becomes_retry_never_pass(self):
        """4. Retry-safe mismatch -> RETRY, never PASS from mismatched receipt."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Retry Safe Mismatch Test",
            "jobs": [
                {
                    "job_id": "job-retry-mismatch-1",
                    "name": "Retry Safe Mismatched Job",
                    "work_order": sample_work_order("job-retry-mismatch-1", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 3,
                    "retry_safe": True,
                }
            ],
        }
        cid = mgr.create_campaign(spec)
        job = mgr.claim_next_job(cid)
        self.assertIsNotNone(job)
        self.assertEqual(job.attempts_used, 1)

        # First attempt returns PASS with wrong job_id
        adapter.set_result(
            job.current_supervisor_job_id,
            SupervisorResult(
                final_status="PASS",
                reason="PASS",
                receipt={
                    "schema_version": "1",
                    "receipt_id": "rcpt-attempt-1-mismatch",
                    "job_id": "wrong-attempt-1-id",
                    "final_status": "PASS",
                    "reason": "PASS",
                },
                receipt_id="rcpt-attempt-1-mismatch",
                receipt_path="/receipts/rcpt-attempt-1-mismatch.json",
            ),
        )

        mgr.dispatch_job(job)

        # Job must NOT be PASS; because retry_safe=True and attempts_used=1 < 3, must be RETRY
        updated_job = mgr.get_job("job-retry-mismatch-1")
        self.assertNotEqual(updated_job.state, JobState.PASS, "Must NEVER mark PASS from mismatched receipt")
        self.assertEqual(updated_job.state, JobState.RETRY)
        self.assertEqual(updated_job.failure_reason, "RECEIPT_IDENTITY_MISMATCH")
        self.assertEqual(updated_job.last_supervisor_receipt_id, "rcpt-attempt-1-mismatch")

        attempts = mgr.get_attempts("job-retry-mismatch-1")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].status, JobState.FAIL)
        self.assertEqual(attempts[0].failure_reason, "RECEIPT_IDENTITY_MISMATCH")
        self.assertEqual(attempts[0].supervisor_receipt_id, "rcpt-attempt-1-mismatch")

        # Prove job can be claimed again for attempt 2
        mgr.release_campaign_lease(cid)
        job_attempt2 = mgr.claim_next_job(cid)
        self.assertIsNotNone(job_attempt2)
        self.assertEqual(job_attempt2.attempts_used, 2)
        self.assertTrue(job_attempt2.current_supervisor_job_id.startswith("job-retry-mismatch-1--a2--"))

    def test_05_real_supervisor_mock_harness_path_returns_correct_execution_job_id(self):
        """5. Real Supervisor mock-harness path returns the correct execution-specific job_id."""
        adapter = RealSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Create work order that writes allowed.txt to satisfy acceptance check
        work_order = sample_work_order("real-sup-id-job", self.workspace, self.receipts, harness="mock")
        (self.workspace / "allowed.txt").write_text("ok", encoding="utf-8")

        spec = {
            "name": "Real Supervisor Execution Identity Test",
            "jobs": [
                {
                    "job_id": "real-sup-id-job",
                    "name": "Mock Real Supervisor Identity Job",
                    "work_order": work_order,
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }

        cid = mgr.create_campaign(spec)
        status = mgr.run_campaign(cid)

        job = mgr.get_job("real-sup-id-job")
        self.assertEqual(job.state, JobState.PASS)
        self.assertEqual(status["counts"][JobState.PASS], 1)
        self.assertIsNotNone(job.current_supervisor_job_id)
        self.assertTrue(job.current_supervisor_job_id.startswith("real-sup-id-job--a1--"))

        # Verify receipt was written to disk by real Supervisor with matching job_id
        receipt_pair = adapter.find_receipt(self.receipts, job.current_supervisor_job_id)
        self.assertIsNotNone(receipt_pair)
        receipt, receipt_path = receipt_pair

        # Proof: Receipt job_id matches current_supervisor_job_id exactly
        self.assertEqual(receipt["final_status"], "PASS")
        self.assertEqual(receipt["job_id"], job.current_supervisor_job_id)
        self.assertTrue(receipt_path.is_file())


if __name__ == "__main__":
    unittest.main()

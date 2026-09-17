from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import CampaignStatus, JobState
from campaign_manager.db import get_connection
from campaign_manager.manager import CampaignManager
from campaign_manager.schema import init_db
from campaign_manager.tests.helpers import sample_campaign_spec


class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_db_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_database_initialization_is_idempotent(self):
        """1. Database initialization is idempotent."""
        init_db(self.db_path)
        init_db(self.db_path)
        init_db(self.db_path)

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute("SELECT count(*) FROM schema_migrations WHERE version = 1")
            count = cur.fetchone()[0]
            self.assertEqual(count, 1)

            # Check tables exist
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            self.assertTrue({"campaigns", "jobs", "dependencies", "events", "schema_migrations"}.issubset(tables))
        finally:
            conn.close()

    def test_02_campaign_and_jobs_persist_across_reopen(self):
        """2. Campaign/jobs persist across process/database reopen."""
        adapter = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Persistence Test", job_count=2)
        cid = mgr1.create_campaign(spec)

        # Discard mgr1 and instantiate a fresh CampaignManager pointing to same SQLite file
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter)
        campaign = mgr2.get_campaign(cid)
        self.assertEqual(campaign.campaign_id, cid)
        self.assertEqual(campaign.name, "Persistence Test")
        self.assertEqual(campaign.status, CampaignStatus.QUEUED)

        job1 = mgr2.get_job("job-1")
        self.assertEqual(job1.state, JobState.QUEUED)
        self.assertEqual(job1.campaign_id, cid)
        self.assertEqual(job1.max_attempts, 2)
        self.assertTrue(job1.retry_safe)

    def test_03_restart_reopen_does_not_lose_queue_position(self):
        """15. Restart/reopen does not lose queue position."""
        adapter = FakeSupervisorAdapter()
        mgr1 = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Queue Position Test", job_count=3)
        # Remove dependencies so all 3 are runnable
        for j in spec["jobs"]:
            j["dependencies"] = []
        cid = mgr1.create_campaign(spec)

        # Claim first job with mgr1
        job1 = mgr1.claim_next_job(cid)
        self.assertIsNotNone(job1)
        self.assertEqual(job1.job_id, "job-1")
        self.assertEqual(job1.state, JobState.RUNNING)
        # Complete job1 via dispatch and release campaign lease
        mgr1.dispatch_job(job1)
        mgr1.release_campaign_lease(cid)

        # Simulate manager restart
        mgr2 = CampaignManager(db_path=self.db_path, adapter=adapter)
        # Next claim should be job-2, preserving exact FIFO order
        job2 = mgr2.claim_next_job(cid)
        self.assertIsNotNone(job2)
        self.assertEqual(job2.job_id, "job-2")
        self.assertEqual(job2.state, JobState.RUNNING)
        mgr2.dispatch_job(job2)
        mgr2.release_campaign_lease(cid)

        # Reopen again and claim job-3
        mgr3 = CampaignManager(db_path=self.db_path, adapter=adapter)
        job3 = mgr3.claim_next_job(cid)
        self.assertIsNotNone(job3)
        self.assertEqual(job3.job_id, "job-3")
        mgr3.dispatch_job(job3)
        mgr3.release_campaign_lease(cid)

        # No more runnable jobs
        self.assertIsNone(mgr3.claim_next_job(cid))

    def test_04_idempotency_prevents_duplicate_logical_dispatch(self):
        """16. Idempotency prevents duplicate logical dispatch/creation."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Idempotency Test", job_count=1)
        spec["jobs"][0]["idempotency_key"] = "unique-key-12345"

        cid = mgr.create_campaign(spec)
        self.assertTrue(cid)

        # Attempting to create a second campaign with the identical job idempotency_key must fail
        spec2 = sample_campaign_spec(self.workspace, self.receipts, name="Duplicate Key Test", job_count=1)
        spec2["jobs"][0]["idempotency_key"] = "unique-key-12345"
        with self.assertRaises(Exception):
            mgr.create_campaign(spec2)


if __name__ == "__main__":
    unittest.main()

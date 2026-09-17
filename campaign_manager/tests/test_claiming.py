from __future__ import annotations

import concurrent.futures
import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.constants import JobState
from campaign_manager.manager import CampaignManager
from campaign_manager.tests.helpers import sample_campaign_spec, sample_work_order


class ClaimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_claim_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_job_claiming_is_atomic_prevents_double_claim(self):
        """7. Job claiming is atomic / prevents double claim."""
        adapter = FakeSupervisorAdapter()
        mgr_setup = CampaignManager(db_path=self.db_path, adapter=adapter)

        spec = {
            "name": "Atomic Claim Test",
            "jobs": [
                {
                    "job_id": "single-job",
                    "name": "Only Job",
                    "work_order": sample_work_order("single-job", self.workspace, self.receipts),
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }
        cid = mgr_setup.create_campaign(spec)

        runner1 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-alpha")
        runner2 = CampaignManager(db_path=self.db_path, adapter=adapter, runner_id="runner-beta")

        from campaign_manager.errors import CampaignAlreadyRunningError

        # Use concurrent thread execution to race claiming the single job
        winner = None
        other_blocked_or_none = False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(runner1.claim_next_job, cid)
            fut2 = executor.submit(runner2.claim_next_job, cid)
            for fut in (fut1, fut2):
                try:
                    res = fut.result()
                    if res is not None:
                        winner = res
                    else:
                        other_blocked_or_none = True
                except CampaignAlreadyRunningError:
                    other_blocked_or_none = True

        self.assertIsNotNone(winner, "Exactly one runner must successfully claim the job")
        self.assertTrue(other_blocked_or_none, "The second runner must be blocked with CampaignAlreadyRunningError or receive None")
        self.assertEqual(winner.job_id, "single-job")
        self.assertEqual(winner.state, JobState.RUNNING)
        self.assertIn(winner.runner_id, {"runner-alpha", "runner-beta"})
        self.assertIsNotNone(winner.claimed_at)
        self.assertIsNotNone(winner.lease_expires_at)

        # Database state verification
        persisted = mgr_setup.get_job("single-job")
        self.assertEqual(persisted.state, JobState.RUNNING)
        self.assertEqual(persisted.runner_id, winner.runner_id)


if __name__ == "__main__":
    unittest.main()

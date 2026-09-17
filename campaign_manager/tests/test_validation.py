from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import FakeSupervisorAdapter
from campaign_manager.db import get_connection
from campaign_manager.errors import CycleDetectedError, ValidationError
from campaign_manager.manager import CampaignManager
from campaign_manager.tests.helpers import sample_campaign_spec, sample_work_order


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_val_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_cycle_detection_simple(self):
        """6. Cycle detection works (2-node cycle)."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Cycle Test", job_count=2)
        # Introduce cycle: job-1 depends on job-2, job-2 depends on job-1
        spec["jobs"][0]["dependencies"] = ["job-2"]
        spec["jobs"][1]["dependencies"] = ["job-1"]

        with self.assertRaises(CycleDetectedError) as ctx:
            mgr.create_campaign(spec)
        self.assertIn("Dependency cycle detected", str(ctx.exception))

    def test_02_cycle_detection_multi_node(self):
        """6. Cycle detection works (multi-node cycle: A -> B -> C -> A)."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Multi-cycle Test", job_count=3)
        spec["jobs"][0]["dependencies"] = ["job-3"]
        spec["jobs"][1]["dependencies"] = ["job-1"]
        spec["jobs"][2]["dependencies"] = ["job-2"]

        with self.assertRaises(CycleDetectedError) as ctx:
            mgr.create_campaign(spec)
        self.assertIn("Dependency cycle detected", str(ctx.exception))

    def test_03_self_dependency_rejected(self):
        """6. Self-dependency rejected."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Self Dep Test", job_count=1)
        spec["jobs"][0]["dependencies"] = ["job-1"]

        with self.assertRaises(CycleDetectedError) as ctx:
            mgr.create_campaign(spec)
        self.assertIn("cannot depend on itself", str(ctx.exception))

    def test_04_unknown_dependency_rejected(self):
        """Unknown dependency rejected."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Unknown Dep Test", job_count=1)
        spec["jobs"][0]["dependencies"] = ["nonexistent-job"]

        with self.assertRaises(ValidationError) as ctx:
            mgr.create_campaign(spec)
        self.assertIn("depends on unknown job", str(ctx.exception))

    def test_05_malformed_campaign_creation_is_atomic_fail_closed(self):
        """18. Malformed campaign creation is atomic/fail-closed."""
        adapter = FakeSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)
        spec = sample_campaign_spec(self.workspace, self.receipts, name="Malformed Campaign", job_count=3)
        
        # Corrupt job 3 by removing required work_order acceptance check
        spec["jobs"][2]["work_order"]["acceptance"] = []

        with self.assertRaises(ValidationError):
            mgr.create_campaign(spec)

        # Verify nothing was saved in SQLite
        conn = get_connection(self.db_path)
        try:
            camp_count = conn.execute("SELECT count(*) FROM campaigns").fetchone()[0]
            job_count = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
            dep_count = conn.execute("SELECT count(*) FROM dependencies").fetchone()[0]
            event_count = conn.execute("SELECT count(*) FROM events").fetchone()[0]

            self.assertEqual(camp_count, 0)
            self.assertEqual(job_count, 0)
            self.assertEqual(dep_count, 0)
            self.assertEqual(event_count, 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

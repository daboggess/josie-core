from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from campaign_manager.adapter import RealSupervisorAdapter
from campaign_manager.constants import JobState
from campaign_manager.manager import CampaignManager


class RealSupervisorAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_real_sup_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        # Supervisor requires workspace to be a git repo or directory
        subprocess.run(["git", "init", "-q", str(self.workspace)], check=True)
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_real_supervisor_adapter_non_destructive_connectivity(self):
        """Verify real adapter discovers and connects to Supervisor without launching an unsafe mutation."""
        adapter = RealSupervisorAdapter()
        info = adapter.verify_connectivity()

        self.assertTrue(info["connected"])
        self.assertTrue(info["supervisor_version"])
        self.assertEqual(info["entrypoint"], "supervisor.run_job.execute")
        self.assertEqual(info["receipt_reader"], "supervisor.receipts.read_receipt")
        self.assertTrue(callable(adapter._execute))
        self.assertTrue(callable(adapter._read_receipt))
        self.assertTrue(callable(adapter._find_receipt))

        # Test non-destructive validation via supervisor's own WorkOrder class
        with self.assertRaises(Exception):
            # Empty dict must fail validation without any process execution
            adapter._work_order_cls.validate({})

    def test_02_real_supervisor_adapter_mock_harness_execution(self):
        """Verify real adapter executes through actual supervisor.run_job.execute using mock harness."""
        adapter = RealSupervisorAdapter()
        mgr = CampaignManager(db_path=self.db_path, adapter=adapter)

        # Build a legitimate work order that supervisor can execute deterministically using its mock harness
        work_order = {
            "schema_version": "1",
            "job_id": "real-sup-mock-1",
            "objective": "allowed",
            "workspace": str(self.workspace),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["allowed.txt"],
            "timeout_seconds": 30,
            "max_attempts": 1,
            "acceptance": [
                {"type": "file_exact", "path": "allowed.txt", "content": "OK"}
            ],
            "prompt_profile": "test",
            "receipt_destination": str(self.receipts),
        }

        spec = {
            "name": "Real Supervisor Mock Harness Test",
            "jobs": [
                {
                    "job_id": "real-sup-mock-1",
                    "name": "Mock Real Supervisor Job",
                    "work_order": work_order,
                    "dependencies": [],
                    "max_attempts": 1,
                    "retry_safe": False,
                }
            ],
        }

        cid = mgr.create_campaign(spec)
        status = mgr.run_campaign(cid)

        job = mgr.get_job("real-sup-mock-1")
        self.assertEqual(job.state, JobState.PASS)
        self.assertEqual(status["counts"][JobState.PASS], 1)
        self.assertIsNotNone(job.last_supervisor_receipt_id)

        # Verify receipt was written to real receipt_destination on disk and is readable via adapter
        receipt_pair = adapter.find_receipt(self.receipts, job.current_supervisor_job_id)
        self.assertIsNotNone(receipt_pair)
        receipt, receipt_path = receipt_pair
        self.assertEqual(receipt["final_status"], "PASS")
        self.assertEqual(receipt["job_id"], job.current_supervisor_job_id)
        self.assertTrue(receipt_path.is_file())


if __name__ == "__main__":
    unittest.main()

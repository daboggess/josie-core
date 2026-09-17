from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from campaign_manager.cli import main
from campaign_manager.tests.helpers import sample_campaign_spec


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="cm_test_cli_"))
        self.db_path = self.tmp_dir / "campaigns.db"
        self.workspace = self.tmp_dir / "workspace"
        self.workspace.mkdir()
        self.receipts = self.tmp_dir / "receipts"
        self.receipts.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_cli_lifecycle(self):
        # 1. init
        with patch("sys.stdout", new=StringIO()) as out:
            ret = main(["--db", str(self.db_path), "init"])
            self.assertEqual(ret, 0)
            self.assertIn("Initialized database schema", out.getvalue())

        # 2. create
        spec = sample_campaign_spec(self.workspace, self.receipts, name="CLI Lifecycle Campaign", job_count=2)
        spec_path = self.tmp_dir / "campaign.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")

        with patch("sys.stdout", new=StringIO()) as out:
            ret = main(["--db", str(self.db_path), "create", str(spec_path)])
            self.assertEqual(ret, 0)
            output = out.getvalue()
            self.assertIn("Campaign created:", output)
            cid = output.strip().split(": ")[1]

        # 3. status before run
        with patch("sys.stdout", new=StringIO()) as out:
            ret = main(["--db", str(self.db_path), "status", cid])
            self.assertEqual(ret, 0)
            output = out.getvalue()
            self.assertIn("QUEUED 2", output)
            self.assertIn("PASS 0", output)

        # 4. status JSON
        with patch("sys.stdout", new=StringIO()) as out:
            ret = main(["--db", str(self.db_path), "status", cid, "--json"])
            self.assertEqual(ret, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["campaign_id"], cid)
            self.assertEqual(data["counts"]["QUEUED"], 2)

        # 5. job inspection
        with patch("sys.stdout", new=StringIO()) as out:
            ret = main(["--db", str(self.db_path), "job", "job-1"])
            self.assertEqual(ret, 0)
            self.assertIn("Job ID:          job-1", out.getvalue())

        # 6. reconcile
        with patch("sys.stdout", new=StringIO()) as out:
            ret = main(["--db", str(self.db_path), "reconcile", cid])
            self.assertEqual(ret, 0)
            self.assertIn("Reconciled 0 jobs", out.getvalue())


if __name__ == "__main__":
    unittest.main()

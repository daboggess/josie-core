import tempfile
import unittest
from pathlib import Path

from josie.backup_verify import BackupItem, main, verify


class BackupVerifyTests(unittest.TestCase):
    def test_existence_only_report_passes_for_present_items(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            report = verify(root, (BackupItem("config", "configuration"),))
            self.assertTrue(report["ok"])
            self.assertEqual(report["mode"], "dry-run")
            self.assertEqual(report["validation_failures"], [])

    def test_missing_required_item_fails_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = verify(
                Path(temporary), (BackupItem("data/josie.db", "database"),)
            )
            self.assertFalse(report["ok"])
            self.assertEqual(report["validation_failures"], ["data/josie.db"])

    def test_cli_exits_nonzero_when_required_inventory_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(main(["--root", temporary, "--json"]), 1)


if __name__ == "__main__":
    unittest.main()

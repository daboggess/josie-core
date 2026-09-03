import json
import tempfile
import unittest
from pathlib import Path

from josie.harbor_freight_phase0b import run_fixture, validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class Phase0BTests(unittest.TestCase):
    def test_repository_manifest_is_valid_and_unverified_is_boolean(self):
        manifest = validate_manifest(ROOT / "config/harbor-freight-backup-manifest.json")
        self.assertTrue(any(e["restore_priority"] == "CORE" for e in manifest["entries"]))
        self.assertTrue(any(e["restore_priority"] == "FULL_DATA" for e in manifest["entries"]))
        self.assertTrue(all(isinstance(e["currently_verified"], bool) for e in manifest["entries"]))

    def test_manifest_rejects_missing_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps({"schema_version": 1, "objectives": {}, "entries": [{"id": "bad"}]}))
            with self.assertRaises(ValueError):
                validate_manifest(path)

    def test_fixture_round_trip_checksums_and_cleans_generated_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "fixture"
            result = run_fixture(root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(len(result["checksums"]), 2)
            self.assertFalse((root / "source").exists())
            self.assertFalse((root / "backup").exists())
            self.assertFalse((root / "restored").exists())

    def test_fixture_refuses_nonempty_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "unrelated.txt").write_text("preserve me")
            with self.assertRaises(ValueError):
                run_fixture(root)
            self.assertEqual((root / "unrelated.txt").read_text(), "preserve me")

    def test_script_default_is_write_free_and_gates_writes(self):
        script = (ROOT / "scripts/Invoke-HarborFreightPhase0B.ps1").read_text()
        self.assertIn("[switch]$WriteRestoreTest", script)
        self.assertIn("if ($WriteRestoreTest)", script)
        self.assertIn("if (-not $WriteRestoreTest)", script)
        self.assertNotIn("Remove-Item -Path", script)
        self.assertNotIn("git push", script.lower())


if __name__ == "__main__":
    unittest.main()

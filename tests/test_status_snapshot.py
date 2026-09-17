"""Unit tests for status snapshot storage calculations and dynamic volume resolution."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from josie.config import Config
from josie.status_snapshot import _read_storage_snapshot


class StatusSnapshotStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _make_config(self, external_path: Path | None) -> Config:
        return Config(
            openai_api_key=None,
            gemini_api_key=None,
            openai_model="gpt-5.6-sol",
            gemini_model="gemini-flash-latest",
            allow_cloud=False,
            log_level="INFO",
            workspace=self.root / "workspace",
            external_storage=external_path,
            ollama_url="http://127.0.0.1:11434",
            local_model="josie-local:1.0",
        )

    def test_storage_snapshot_dynamically_resolves_external_drive(self):
        fake_snapshot = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "warning_below_gb": 20,
            "critical_below_gb": 15,
            "drives": [
                {"drive": "C:\\", "total_gb": 120.0, "free_gb": 25.4},
                {"drive": "D:\\", "total_gb": 110.0, "free_gb": 105.0},
                {"drive": "I:\\", "total_gb": 9313.9, "free_gb": 8618.1},
            ],
            "cloud_activity": False,
            "deletion_performed": False,
        }
        with patch.object(Path, "read_text", return_value=json.dumps(fake_snapshot)):
            config = self._make_config(Path("I:/Josie-Storage"))
            result = _read_storage_snapshot(config)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["system_free_gb"], 25.4)
        self.assertEqual(result["external_free_gb"], 8618.1)

    def test_storage_snapshot_missing_config_returns_critical(self):
        config = self._make_config(None)
        result = _read_storage_snapshot(config)
        self.assertEqual(result["status"], "critical")
        self.assertIsNone(result["system_free_gb"])
        self.assertIsNone(result["external_free_gb"])

    def test_storage_snapshot_stale_returns_critical(self):
        stale_snapshot = {
            "schema_version": 1,
            "created_at": "2020-01-01T00:00:00+00:00",
            "status": "ok",
            "warning_below_gb": 20,
            "critical_below_gb": 15,
            "drives": [
                {"drive": "C:\\", "total_gb": 120.0, "free_gb": 25.0},
                {"drive": "I:\\", "total_gb": 9313.9, "free_gb": 8618.1},
            ],
            "cloud_activity": False,
            "deletion_performed": False,
        }
        with patch.object(Path, "read_text", return_value=json.dumps(stale_snapshot)):
            config = self._make_config(Path("I:/Josie-Storage"))
            result = _read_storage_snapshot(config)

        self.assertEqual(result["status"], "critical")
        self.assertIsNone(result["system_free_gb"])
        self.assertIsNone(result["external_free_gb"])


if __name__ == "__main__":
    unittest.main()

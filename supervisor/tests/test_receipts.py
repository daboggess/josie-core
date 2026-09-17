from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from supervisor.receipts import find_receipt, read_receipt, write_receipt


class ReceiptsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_read_receipt_returns_written_payload(self):
        payload = {
            "schema_version": "1",
            "supervisor_version": "0.1",
            "job_id": "test-job-01",
            "final_status": "PASS",
            "reason": "PASS",
        }
        path = write_receipt(self.directory, payload, receipt_id="receipt-01")
        data = read_receipt(path)

        self.assertIsInstance(data, dict)
        self.assertEqual(data["schema_version"], "1")
        self.assertEqual(data["job_id"], "test-job-01")
        self.assertEqual(data["receipt_id"], "receipt-01")
        self.assertEqual(data["final_status"], "PASS")

    def test_02_read_receipt_accepts_string_path(self):
        payload = {
            "schema_version": "1",
            "job_id": "test-job-str",
            "final_status": "PASS",
        }
        path = write_receipt(self.directory, payload, receipt_id="receipt-str")
        data = read_receipt(str(path))
        self.assertEqual(data["receipt_id"], "receipt-str")

    def test_03_read_receipt_missing_file_raises_filenotfound(self):
        missing = self.directory / "nonexistent.json"
        with self.assertRaises(FileNotFoundError):
            read_receipt(missing)

    def test_04_read_receipt_invalid_json_raises_value_error(self):
        bad_file = self.directory / "corrupt.json"
        bad_file.write_text("not json content", encoding="utf-8")
        with self.assertRaises(ValueError):
            read_receipt(bad_file)

    def test_05_read_receipt_missing_required_fields_raises_value_error(self):
        # Missing receipt_id
        missing_id = self.directory / "no_id.json"
        missing_id.write_text(json.dumps({"schema_version": "1"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            read_receipt(missing_id)

        # Missing schema_version
        missing_schema = self.directory / "no_schema.json"
        missing_schema.write_text(json.dumps({"receipt_id": "r1"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            read_receipt(missing_schema)

        # Not a dictionary
        not_dict = self.directory / "not_dict.json"
        not_dict.write_text(json.dumps(["item1"]), encoding="utf-8")
        with self.assertRaises(ValueError):
            read_receipt(not_dict)

    def test_06_find_receipt_finds_matching_job(self):
        r1 = write_receipt(self.directory, {"schema_version": "1", "job_id": "job-alpha"}, receipt_id="r1")
        r2 = write_receipt(self.directory, {"schema_version": "1", "job_id": "job-beta"}, receipt_id="r2")

        found = find_receipt(self.directory, "job-alpha")
        self.assertIsNotNone(found)
        receipt_dict, path = found
        self.assertEqual(receipt_dict["job_id"], "job-alpha")
        self.assertEqual(path.resolve(), r1.resolve())

    def test_07_find_receipt_returns_most_recent_for_same_job(self):
        r_old = write_receipt(self.directory, {"schema_version": "1", "job_id": "job-multi", "attempt": 1}, receipt_id="r-old")
        time.sleep(0.05)
        r_new = write_receipt(self.directory, {"schema_version": "1", "job_id": "job-multi", "attempt": 2}, receipt_id="r-new")

        # Explicitly set mtimes to guarantee ordering
        now = time.time()
        os.utime(r_old, (now - 10, now - 10))
        os.utime(r_new, (now, now))

        found = find_receipt(self.directory, "job-multi")
        self.assertIsNotNone(found)
        receipt_dict, path = found
        self.assertEqual(receipt_dict["receipt_id"], "r-new")
        self.assertEqual(receipt_dict["attempt"], 2)
        self.assertEqual(path.resolve(), r_new.resolve())

    def test_08_find_receipt_returns_none_when_not_found(self):
        write_receipt(self.directory, {"schema_version": "1", "job_id": "job-other"}, receipt_id="r-other")
        self.assertIsNone(find_receipt(self.directory, "job-absent"))

    def test_09_find_receipt_returns_none_for_missing_directory(self):
        self.assertIsNone(find_receipt(self.directory / "does_not_exist", "job-any"))

    def test_10_find_receipt_safely_skips_corrupted_and_temporary_files(self):
        # Corrupted JSON file
        broken = self.directory / "broken.json"
        broken.write_text("corrupted", encoding="utf-8")

        # Temporary / hidden file
        tmp = self.directory / ".hidden.json.tmp"
        tmp.write_text("temporary", encoding="utf-8")

        # Valid receipt
        valid = write_receipt(self.directory, {"schema_version": "1", "job_id": "job-valid"}, receipt_id="r-valid")

        found = find_receipt(self.directory, "job-valid")
        self.assertIsNotNone(found)
        receipt_dict, path = found
        self.assertEqual(receipt_dict["job_id"], "job-valid")
        self.assertEqual(path.resolve(), valid.resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from supervisor.verifier import attribute_changes


class ArtifactAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.logs = self.root / "data" / "private" / "supervisor-local-code" / "logs"
        self.logs.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_01_exact_stdout_is_supervisor_owned(self):
        stdout = self.logs / "job.stdout.log"
        worker, owned = attribute_changes(
            [stdout.relative_to(self.root).as_posix()], self.root, [stdout]
        )
        self.assertEqual(worker, [])
        self.assertEqual(owned, ["data/private/supervisor-local-code/logs/job.stdout.log"])

    def test_02_exact_stderr_event_and_receipt_are_supervisor_owned(self):
        paths = [self.logs / "job.stderr.log", self.logs / "job.events.jsonl",
                 self.root / "data/private/supervisor-local-code/receipt.json"]
        relative = [path.relative_to(self.root).as_posix() for path in paths]
        worker, owned = attribute_changes(relative, self.root, paths)
        self.assertEqual(worker, [])
        self.assertEqual(owned, sorted(relative))

    def test_03_allowed_worker_source_still_counts(self):
        worker, _ = attribute_changes(["src/value.py"], self.root, [self.logs / "job.stdout.log"])
        self.assertEqual(worker, ["src/value.py"])

    def test_04_unauthorized_normal_path_still_counts(self):
        worker, _ = attribute_changes(["README.md"], self.root, [self.logs / "job.stdout.log"])
        self.assertEqual(worker, ["README.md"])

    def test_05_fake_log_is_not_excluded(self):
        registered = self.logs / "job.stdout.log"
        fake = "data/private/supervisor-local-code/logs/fake.stdout.log"
        worker, _ = attribute_changes([fake], self.root, [registered])
        self.assertEqual(worker, [fake])

    def test_06_logs_directory_is_not_globally_ignored(self):
        fake = "data/private/supervisor-local-code/logs/anything.log"
        worker, owned = attribute_changes([fake], self.root, [])
        self.assertEqual(worker, [fake])
        self.assertEqual(owned, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

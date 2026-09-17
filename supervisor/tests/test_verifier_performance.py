from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from supervisor.verifier import changed_paths, scope_violations, snapshot
from supervisor.work_order import WorkOrder

ROOT = Path(r"D:\Josie")


class VerifierPerformanceTests(unittest.TestCase):
    def test_01_snapshot_runs_under_two_seconds(self):
        start = time.perf_counter()
        result = snapshot(ROOT)
        duration = time.perf_counter() - start
        self.assertLess(duration, 2.0, f"Snapshot took {duration:.3f}s, expected < 2.0s")
        self.assertIn("files", result)
        self.assertGreater(len(result["files"]), 100)

    def test_02_snapshot_preserves_non_runtime_data_files(self):
        result = snapshot(ROOT)
        # Check that configuration / data files outside data/private are preserved
        self.assertIn("data/deployment-state.json", result["files"])
        self.assertIn("data/system-gate-state.json", result["files"])
        self.assertIn("core.py", result["files"])

    def test_03_snapshot_excludes_proven_runtime_directories(self):
        result = snapshot(ROOT)
        for path in result["files"]:
            self.assertFalse(
                path.startswith("data/private/"),
                f"Unexpected runtime path in snapshot: {path}"
            )
            self.assertFalse(
                path.startswith("data/backups/"),
                f"Unexpected backup path in snapshot: {path}"
            )
            self.assertFalse(
                path.startswith("models/"),
                f"Unexpected model blob in snapshot: {path}"
            )
            self.assertFalse(
                path.startswith(".venv/"),
                f"Unexpected virtualenv path in snapshot: {path}"
            )
            self.assertFalse(
                "node_modules" in path,
                f"Unexpected node_modules in snapshot: {path}"
            )

    def test_04_unauthorized_source_modification_is_detected_and_violates_scope(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            allowed_file = workspace / "allowed.py"
            unauthorized_file = workspace / "core_logic.py"
            allowed_file.write_text("print('initial')", encoding="utf-8")
            unauthorized_file.write_text("SECRET = 1", encoding="utf-8")

            order = WorkOrder.validate({
                "schema_version": "1",
                "job_id": "test-scope-job",
                "objective": "Only modify allowed.py",
                "workspace": str(workspace),
                "harness": "mock",
                "model": "mock/model",
                "allowed_changed_paths": ["allowed.py"],
                "acceptance": [{"type": "file_exists", "path": "allowed.py"}],
                "max_attempts": 1,
                "timeout_seconds": 60,
                "prompt_profile": "test",
                "receipt_destination": str(workspace),
            })

            before = snapshot(workspace, order.allowed_changed_paths)

            # Simulate worker modifying both allowed and unauthorized files
            allowed_file.write_text("print('modified')", encoding="utf-8")
            unauthorized_file.write_text("SECRET = 2", encoding="utf-8")

            after = snapshot(workspace, order.allowed_changed_paths)
            changes = changed_paths(before, after)

            self.assertIn("allowed.py", changes)
            self.assertIn("core_logic.py", changes)

            violations = scope_violations(changes, order)
            self.assertEqual(violations, ["core_logic.py"])

    def test_05_unauthorized_file_creation_is_detected_and_violates_scope(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            allowed_file = workspace / "task.txt"
            allowed_file.write_text("task", encoding="utf-8")

            order = WorkOrder.validate({
                "schema_version": "1",
                "job_id": "test-creation-job",
                "objective": "Modify task.txt",
                "workspace": str(workspace),
                "harness": "mock",
                "model": "mock/model",
                "allowed_changed_paths": ["task.txt"],
                "acceptance": [{"type": "file_exists", "path": "task.txt"}],
                "max_attempts": 1,
                "timeout_seconds": 60,
                "prompt_profile": "test",
                "receipt_destination": str(workspace),
            })

            before = snapshot(workspace, order.allowed_changed_paths)

            # Worker creates an unauthorized unexpected file
            rogue = workspace / "backdoor.py"
            rogue.write_text("import os", encoding="utf-8")

            after = snapshot(workspace, order.allowed_changed_paths)
            changes = changed_paths(before, after)

            self.assertIn("backdoor.py", changes)
            violations = scope_violations(changes, order)
            self.assertIn("backdoor.py", violations)


if __name__ == "__main__":
    unittest.main(verbosity=2)

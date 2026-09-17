import shutil
import sys
import time
import unittest
import uuid
from pathlib import Path

from supervisor.authority import supervised_environment
from supervisor.process_control import run_contained
from supervisor.verifier import run_acceptance
from supervisor.work_order import WorkOrder


class ArtifactSuppressionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".artifact-tmp" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        (self.root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(Path(__file__).parent / ".artifact-tmp", ignore_errors=True)

    def test_01_supervised_environment_sets_scoped_controls(self):
        env = supervised_environment({"KEEP": "yes"})
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(env["PYTEST_ADDOPTS"], "-p no:cacheprovider")
        self.assertEqual(env["KEEP"], "yes")

    def test_02_worker_child_inherits_and_creates_no_bytecode(self):
        out, err = self.root / "out.log", self.root / "err.log"
        result = run_contained([sys.executable, "-c", "import os, sample; print(os.environ['PYTHONDONTWRITEBYTECODE'])"], str(self.root), 10, str(out), str(err), env=supervised_environment())
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(out.read_text().strip(), "1")
        self.assertFalse((self.root / "__pycache__").exists())
        self.assertTrue(result.liveness["process_created"])
        self.assertIsNotNone(result.liveness["first_stdout_at"])
        self.assertTrue(result.liveness["meaningful_worker_activity_observed"])

    def test_03_child_process_is_not_mistaken_for_worker_activity(self):
        out, err = self.root / "silent-out.log", self.root / "silent-err.log"
        result = run_contained(
            [sys.executable, "-c", "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)']); time.sleep(5)"],
            str(self.root), 1, str(out), str(err), env=supervised_environment())
        self.assertTrue(result.timed_out)
        self.assertTrue(result.liveness["observed_child_pids"])
        self.assertIsNone(result.liveness["first_stdout_at"])
        self.assertIsNone(result.liveness["first_stderr_at"])
        self.assertFalse(result.liveness["meaningful_worker_activity_observed"])

    def test_04_acceptance_subprocess_inherits_and_creates_no_bytecode(self):
        raw = {"schema_version": "1", "job_id": "artifact-test", "objective": "test",
               "workspace": str(self.root), "harness": "mock", "model": "mock/exact",
               "allowed_changed_paths": ["sample.py"], "timeout_seconds": 5, "max_attempts": 1,
               "acceptance": [{"type": "command", "argv": [sys.executable, "-c", "import os, sample; print(os.environ['PYTHONDONTWRITEBYTECODE']); print(os.environ['PYTEST_ADDOPTS'])"]}],
               "prompt_profile": "test", "receipt_destination": str(self.root.parent / "receipts")}
        result = run_acceptance(WorkOrder.validate(raw), [])[0]
        self.assertTrue(result["passed"])
        self.assertIn("1\n-p no:cacheprovider", result["stdout"])
        self.assertFalse((self.root / "__pycache__").exists())

    def test_05_no_tool_activity_stall_terminates_process(self):
        out, err = self.root / "stall-out.log", self.root / "stall-err.log"
        started = time.monotonic()
        result = run_contained(
            [sys.executable, "-c", "import time; print('thinking', flush=True); time.sleep(10)"],
            str(self.root), 5, str(out), str(err), env=supervised_environment(),
            meaningful_activity_probe=lambda: False, stall_timeout=0.25)
        self.assertTrue(result.stalled)
        self.assertFalse(result.timed_out)
        self.assertLess(time.monotonic() - started, 3)
        self.assertFalse(result.liveness["meaningful_tool_activity_observed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

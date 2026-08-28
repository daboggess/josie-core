"""Safety regressions for the opt-in diagnostics; no real services are contacted."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doctor = load_script("josie_doctor")
benchmark = load_script("measure_pre_gpu")


class DoctorTests(unittest.TestCase):
    def test_network_only_allows_exact_local_gets(self):
        for url in ("https://example.com", "http://127.0.0.1:11434/api/chat",
                    "http://127.0.0.1:8790/v1/delegate/codex", "http://localhost:11434/api/tags"):
            with self.assertRaises(ValueError):
                doctor.get_json(url)

    def test_redirects_are_forbidden(self):
        with self.assertRaises(ValueError):
            doctor.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_command_failure_and_timeout_withhold_raw_output(self):
        failure = subprocess.CompletedProcess(["diagnostic"], 1, "secret-output", "secret-error")
        with patch.object(doctor.subprocess, "run", return_value=failure) as execute:
            self.assertEqual(doctor.run_read(["diagnostic"]), (False, ""))
            self.assertFalse(execute.call_args.kwargs["shell"])
            self.assertEqual(execute.call_args.kwargs["timeout"], 15)
        with patch.object(doctor.subprocess, "run", side_effect=subprocess.TimeoutExpired("diagnostic", 1)):
            self.assertEqual(doctor.run_read(["diagnostic"]), (False, ""))

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.db"
            self.assertFalse(doctor.sqlite_health(path)[0])
            self.assertFalse(path.exists())

    def test_database_integrity_check_preserves_bytes_and_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.db"
            with contextlib.closing(sqlite3.connect(path)) as connection:
                with connection:
                    connection.execute("CREATE TABLE example(value TEXT)")
                    connection.execute("INSERT INTO example VALUES ('private fixture')")
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(doctor.sqlite_health(path), (True, "quick_check=True"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_missing_nvidia_is_warning_not_failure_or_installation(self):
        report = doctor.Report()
        with patch.object(doctor, "run_read") as command:
            doctor.check_gpu(report, [{"Name": "Intel HD Graphics 630"}], None)
        command.assert_not_called()
        self.assertTrue(report.rows)
        self.assertTrue(all(row["status"] == "WARN" for row in report.rows))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(report.finish(), 0)

    def test_expected_model_missing_fails_but_idle_is_not_failure(self):
        report = doctor.Report()
        doctor.check_models(report, {"models": []}, {"models": []})
        self.assertEqual(report.rows[0]["status"], "FAIL")
        report = doctor.Report()
        doctor.check_models(report, {"models": [{"name": doctor.EXPECTED_MODEL, "size": 1}]}, {"models": []})
        self.assertNotIn("FAIL", [row["status"] for row in report.rows])

    def test_cpu_residency_is_reported_without_forcing_gpu(self):
        report = doctor.Report()
        doctor.check_models(report, {"models": [{"name": doctor.EXPECTED_MODEL}]},
                            {"models": [{"name": doctor.EXPECTED_MODEL, "size_vram": 0}]})
        self.assertTrue(any(row["check"] == "Ollama GPU use" and row["status"] == "WARN" for row in report.rows))

    def test_benchmark_requires_explicit_opt_in(self):
        with patch.object(benchmark, "measure") as measure, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(benchmark.main([]), 0)
        measure.assert_not_called()
        self.assertEqual(benchmark.OPTIONS["num_predict"], 128)
        self.assertEqual(benchmark.MODEL, doctor.EXPECTED_MODEL)

    def test_doctor_has_no_mutating_native_commands_or_inference(self):
        import re
        self.assertIsNone(re.search(r"\b(?:Set|Remove|Start|Stop|Restart|Install|Enable|Disable|New)-[A-Za-z]",
                                    doctor.WINDOWS_QUERY))
        source = (ROOT / "scripts/josie_doctor.py").read_text(encoding="utf-8")
        for forbidden in ("shell=True", "LocalStore(", 'method="POST"', '"/api/generate"', '"/api/chat"',
                          '"restart"', '"pull"', '"prune"', '"down"', "pip install", "npm install"):
            self.assertNotIn(forbidden, source)
        wrapper = (ROOT / "josie-doctor.sh").read_text(encoding="utf-8")
        self.assertIn(".venv/Scripts/python.exe", wrapper)
        self.assertIn(' -B ', wrapper)
        self.assertNotIn("sudo", wrapper)


if __name__ == "__main__":
    unittest.main()

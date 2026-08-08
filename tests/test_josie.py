from __future__ import annotations

import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from josie.config import load_config
from josie.tools import available_tools, run_tool
from josie.providers import probe_openai, provider_status
from josie.gui import respond
from josie.storage import LocalStore
from josie.diagnostics import recovery_snapshot, system_snapshot, uptime_snapshot
from josie.reports import export_diagnostics, warning_snapshot
from josie.instance import gui_instance
from josie.roadmap import roadmap_summary


class JosieTests(unittest.TestCase):
    def test_health_is_allowlisted_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(root / ".env")
            result = run_tool("health", config=config, project_root=root)
            self.assertIn("health", available_tools())
            self.assertEqual(result["status"], "ok")

    def test_unknown_tool_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(root / ".env")
            with self.assertRaises(ValueError):
                run_tool("shell", config=config, project_root=root)

    def test_provider_status_never_exposes_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENAI_API_KEY=secret-one\nGEMINI_API_KEY=secret-two\n")
            result = provider_status(load_config(root / ".env"))
            rendered = str(result)
            self.assertNotIn("secret-one", rendered)
            self.assertNotIn("secret-two", rendered)
            self.assertTrue(result["openai"]["configured"])
            self.assertTrue(result["gemini"]["configured"])

    def test_cloud_calls_are_spend_locked_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENAI_API_KEY=secret-one\n")
            config = load_config(root / ".env")
            self.assertFalse(config.allow_cloud)
            with self.assertRaisesRegex(RuntimeError, "disabled"):
                probe_openai(config)

    def test_gui_unknown_request_stays_local(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(root / ".env")
            answer = respond("invent something new", config=config, project_root=root)
            self.assertIn("not sent", answer)

    def test_gui_reports_cloud_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(root / ".env")
            answer = respond("cloud status", config=config, project_root=root)
            self.assertIn("LOCKED OFF", answer)

    def test_local_memory_and_tasks_persist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            config = load_config(root / ".env")
            self.assertIn("Remembered locally", respond("remember GPU is postponed", config=config, project_root=root, store=store))
            self.assertIn("GPU is postponed", respond("memories", config=config, project_root=root, store=store))
            self.assertIn("Added task 1", respond("add task check SSD health", config=config, project_root=root, store=store))
            self.assertIn("check SSD health", respond("tasks", config=config, project_root=root, store=store))
            self.assertIn("marked complete", respond("complete task 1", config=config, project_root=root, store=store))
            self.assertEqual(respond("tasks", config=config, project_root=root, store=store), "No pending tasks.")

    def test_local_status_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            store.remember("A local fact")
            store.add_task("A pending task")
            config = load_config(root / ".env")
            answer = respond("status", config=config, project_root=root, store=store)
            self.assertIn("Pending tasks: 1", answer)
            self.assertIn("Memories: 1", answer)
            self.assertIn("Cloud: LOCKED OFF", answer)

    def test_system_monitor_is_local_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(root / ".env")
            snapshot = system_snapshot(config=config, project_root=root)
            self.assertGreater(snapshot["cpu_logical_count"], 0)
            self.assertGreater(snapshot["disk_total_gb"], 0)
            self.assertFalse(snapshot["cloud_calls_allowed"])
            answer = respond("system status", config=config, project_root=root)
            self.assertIn("logical CPUs", answer)

    def test_monitoring_tools_are_explicitly_allowlisted(self) -> None:
        self.assertIn("system", available_tools())
        self.assertIn("repository", available_tools())
        self.assertIn("storage", available_tools())
        self.assertIn("uptime", available_tools())
        self.assertIn("recovery", available_tools())
        self.assertIn("external-storage", available_tools())

    def test_uptime_monitor_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = load_config(root / ".env")
            snapshot = uptime_snapshot(config=config, project_root=root)
            self.assertGreater(snapshot["uptime_seconds"], 0)
            self.assertIn("Windows uptime", respond("uptime", config=config, project_root=root))

    def test_approvals_record_decisions_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            config = load_config(root / ".env")
            requested = respond("request action inspect the SSD", config=config, project_root=root, store=store)
            self.assertIn("Nothing has been executed", requested)
            self.assertIn("inspect the SSD", respond("approvals", config=config, project_root=root, store=store))
            decided = respond("approve 1", config=config, project_root=root, store=store)
            self.assertIn("No action was executed", decided)
            self.assertEqual(respond("approvals", config=config, project_root=root, store=store), "No pending approvals.")
            self.assertIn("approval_approved", respond("activity", config=config, project_root=root, store=store))

    def test_daily_backup_is_local_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            store.remember("survives backup")
            backup = store.create_daily_backup(root / "data" / "backups")
            self.assertTrue(backup.exists())
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(connection.execute("SELECT content FROM memories").fetchone()[0], "survives backup")
            config = load_config(root / ".env")
            recovery = recovery_snapshot(config=config, project_root=root)
            self.assertEqual(recovery["integrity"], "ok")
            self.assertEqual(recovery["backup_count"], 1)

    def test_local_reminder_is_persistent_and_nonexecuting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            config = load_config(root / ".env")
            answer = respond("remind me in 5 minutes to check Josie", config=config, project_root=root, store=store)
            self.assertIn("set locally", answer)
            self.assertIn("check Josie", respond("reminders", config=config, project_root=root, store=store))

    def test_secret_free_diagnostics_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENAI_API_KEY=top-secret\nGEMINI_API_KEY=also-secret\n")
            config = load_config(root / ".env")
            LocalStore(root / "data" / "josie.db").create_daily_backup(root / "data" / "backups")
            report = export_diagnostics(config=config, project_root=root)
            content = report.read_text(encoding="utf-8")
            self.assertNotIn("top-secret", content)
            self.assertNotIn("also-secret", content)
            self.assertIn('"cloud_calls_allowed": false', content)

    def test_external_storage_config_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(load_config(root / ".env").external_storage)
            external = root / "external"
            external.mkdir()
            (root / ".env").write_text(f"JOSIE_EXTERNAL_STORAGE={external}\n")
            self.assertEqual(load_config(root / ".env").external_storage, external.resolve())

    def test_gui_single_instance_guard(self) -> None:
        with gui_instance("Local\\JosieCoreTestMutex") as first:
            self.assertTrue(first)
            with gui_instance("Local\\JosieCoreTestMutex") as second:
                self.assertFalse(second)

    def test_canonical_roadmap_is_queryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "JOSIE_SETUP_CHECKLIST.md").write_text(
                "# Roadmap\n\n- [x] Done\n- [ ] Pending\n\n## Critical path\n\n1. First safe step.\n",
                encoding="utf-8",
            )
            summary = roadmap_summary(root)
            self.assertEqual(summary["completed"], 1)
            self.assertEqual(summary["pending"], 1)
            self.assertEqual(summary["critical_path"], ["First safe step."])
            config = load_config(root / ".env")
            self.assertIn("1 completed", respond("roadmap", config=config, project_root=root))
            self.assertIn("First safe step", respond("next step", config=config, project_root=root))


if __name__ == "__main__":
    unittest.main()

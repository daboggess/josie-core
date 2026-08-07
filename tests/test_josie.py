from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from josie.config import load_config
from josie.tools import available_tools, run_tool
from josie.providers import probe_openai, provider_status
from josie.gui import respond
from josie.storage import LocalStore


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


if __name__ == "__main__":
    unittest.main()

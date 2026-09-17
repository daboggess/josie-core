from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from supervisor.authority import authorize_command, secure_agent


class TrustedSupervisedJobTests(unittest.TestCase):
    def setUp(self):
        self.config = {"agent": {"josie-coder": {}}}
        secure_agent(self.config, "josie-coder", set())
        self.permission = self.config["agent"]["josie-coder"]["permission"]

    def load_filter(self):
        path = Path(r"D:\Josie\deploy\open-webui\exact-tool-response-filter.py")
        spec = importlib.util.spec_from_file_location("trusted_filter_test", path)
        module = importlib.util.module_from_spec(spec)
        stub = types.ModuleType("pydantic")
        stub.BaseModel = object
        stub.Field = lambda *, default: default
        with patch.dict(sys.modules, {"pydantic": stub}):
            spec.loader.exec_module(module)
        return module

    def test_01_explicit_prefix_starts_trusted_supervised_mode(self):
        module = self.load_filter()
        body = {"model": module.MODEL_ID, "chat_id": "trusted-start", "messages": [
            {"role": "user", "content": "Delegate Local Code:\nWorkspace: D:\\fixture\nTask:\nedit\nAllowed changes:\na.py\nAcceptance:\ncommand: python -m unittest"}
        ], "tool_ids": ["server:josie-subscription-seats/delegate_local_code"]}
        response = {"assistant_message": "JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: PASS"}
        with patch.object(module, "_record_history"), patch.object(
                module, "_control_post", return_value=response) as dispatch:
            updated = module.Filter().inlet(body)
        dispatch.assert_called_once()
        self.assertEqual(updated["tool_ids"], [])

    def test_02_read_search_glob_are_allowed_without_ask(self):
        for tool in ("read", "list", "glob", "grep"):
            self.assertEqual(self.permission[tool], "allow")

    def test_03_authorized_edit_tool_is_allowed_without_ask(self):
        for tool in ("write", "edit", "apply_patch"):
            self.assertEqual(self.permission[tool], "allow")

    def test_04_existing_test_commands_are_allowed_without_ask(self):
        self.assertEqual(self.permission["bash"]["*"], "allow")
        self.assertTrue(authorize_command("python -m unittest -v", set())["allowed"])

    def test_05_acceptance_command_is_allowed_without_ask(self):
        self.assertTrue(authorize_command(
            r"D:\Josie\.venv\Scripts\python.exe -m unittest -v", set())["allowed"])

    def test_06_bookkeeping_tools_are_removed_not_approval_gated(self):
        self.assertEqual(self.permission["task"], "deny")
        self.assertNotEqual(self.permission.get("task"), "ask")
        self.assertEqual(self.permission["todowrite"], "allow")

    def test_07_package_install_remains_denied(self):
        self.assertFalse(authorize_command("python -m pip install pytest", set())["allowed"])

    def test_08_external_directory_access_remains_denied(self):
        self.assertEqual(self.permission["external_directory"], "deny")

    def test_09_external_network_remains_denied(self):
        self.assertFalse(authorize_command("curl https://example.com", set())["allowed"])

    def test_10_host_mutation_remains_denied(self):
        self.assertFalse(authorize_command("setx JOSIE_TEST value", set())["allowed"])
        self.assertFalse(authorize_command("git reset --hard", set())["allowed"])
        self.assertFalse(authorize_command("git clean -fd", set())["allowed"])
        self.assertFalse(authorize_command("taskkill /PID 123 /T /F", set())["allowed"])

    def test_11_terminal_result_blocks_further_model_tool_activity(self):
        module = self.load_filter()
        raw = "Delegate Local:\nWorkspace: D:\\fixture\nTask:\nedit\nAllowed changes:\na.py\nAcceptance:\ncommand: python -m unittest"
        body = {"model": module.MODEL_ID, "chat_id": "trusted-terminal", "messages": [
            {"role": "user", "content": raw},
            {"role": "assistant", "content": "create README and call more tools"},
        ], "tool_ids": ["server:josie-subscription-seats/delegate_local_code"]}
        response = {"assistant_message": "JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: PASS"}
        with patch.object(module, "_record_history"), patch.object(
                module, "_control_post", return_value=response) as dispatch:
            inlet = module.Filter().inlet(body)
            outlet = asyncio.run(module.Filter().outlet(inlet))
        dispatch.assert_called_once()
        self.assertEqual(inlet["tool_ids"], [])
        self.assertEqual(outlet["messages"][-1]["content"], response["assistant_message"])

    def test_12_ordinary_chat_permissions_are_unchanged(self):
        module = self.load_filter()
        body = {"model": module.MODEL_ID, "messages": [
            {"role": "user", "content": "Hello"}
        ], "tool_ids": ["server:josie-subscription-seats/delegate_local_code"]}
        with patch.object(module, "_record_history"), patch.object(module, "_control_post") as dispatch:
            updated = module.Filter().inlet(body)
        dispatch.assert_not_called()
        self.assertEqual(updated["tool_ids"], body["tool_ids"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.authority import bash_permission_rules, execute_if_authorized, secure_agent


class AuthorityTests(unittest.TestCase):
    def test_01_package_install_blocked_before_mutation(self):
        mutated = []
        decision, result = execute_if_authorized("pip install pytest", set(), lambda: mutated.append(True))
        self.assertFalse(decision["allowed"])
        self.assertTrue(decision["prevented_before_execution"])
        self.assertEqual(mutated, [])
        self.assertIsNone(result)
        config = {"agent": {"josie-coder": {}}}
        secure_agent(config, "josie-coder", set())
        self.assertEqual(config["agent"]["josie-coder"]["permission"]["bash"]["*pip install*"], "deny")

    def test_02_explicit_package_install_capability_representable(self):
        decision, _ = execute_if_authorized("python -m pip install example", {"package_installs"}, lambda: "not-an-install")
        self.assertTrue(decision["allowed"])
        self.assertEqual(bash_permission_rules({"package_installs"})["*winget install*"], "deny")

    def test_03_safe_test_execution_allowed(self):
        called = []
        decision, result = execute_if_authorized("python -m unittest -v", set(), lambda: called.append("ran") or 0)
        self.assertTrue(decision["allowed"])
        self.assertEqual(result, 0)
        self.assertEqual(called, ["ran"])

    def test_04_josie_coder_profile_permission_order_and_tools(self):
        profile = ROOT / ".opencode" / "agents" / "josie-coder.md"
        self.assertTrue(profile.is_file())
        config = {"agent": {"josie-coder": {}}}
        secure_agent(config, "josie-coder", set(), profile_path=profile)
        perm = config["agent"]["josie-coder"]["permission"]
        keys = list(perm.keys())
        self.assertEqual(keys[0], "*")
        self.assertEqual(perm["*"], "deny")
        for tool in ("read", "write", "edit", "apply_patch", "glob", "grep", "list", "bash", "todowrite"):
            self.assertIn(tool, perm)
            if tool == "bash":
                self.assertEqual(perm["bash"]["*"], "allow")
            else:
                self.assertEqual(perm[tool], "allow")

    def test_05_profile_without_leading_wildcard_deny_raises(self):
        with tempfile.TemporaryDirectory() as td:
            bad_profile = Path(td) / "bad-agent.md"
            bad_profile.write_text(
                "---\n"
                "description: test\n"
                "mode: primary\n"
                "permission:\n"
                "  read: allow\n"
                "  edit: allow\n"
                "---\n\n"
                "Prompt body\n",
                encoding="utf-8",
            )
            config = {"agent": {"bad-agent": {}}}
            with self.assertRaisesRegex(ValueError, "must declare '\\*' as the first permission rule"):
                secure_agent(config, "bad-agent", set(), profile_path=bad_profile)

    def test_06_permission_dict_serializes_wildcard_deny_first(self):
        config = {"agent": {"josie-coder": {}}}
        secure_agent(config, "josie-coder", set())
        serialized = json.dumps(config["agent"]["josie-coder"]["permission"])
        self.assertTrue(serialized.startswith('{"*": "deny"'))


if __name__ == "__main__":
    unittest.main(verbosity=2)

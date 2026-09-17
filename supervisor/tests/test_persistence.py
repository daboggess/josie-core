import unittest
from pathlib import Path

from supervisor.policy import classify_premature_stop, should_retry
from supervisor.prompt_compiler import compile_prompt
from supervisor.work_order import WorkOrder


def evidence(**overrides):
    values = {
        "requires_modification": True,
        "exit_code": 0,
        "timed_out": False,
        "violations": [],
        "changes": [],
        "acceptance": [{"passed": False}],
        "tool_names": ["glob", "read"],
        "blocker_reported": False,
        "denied_actions": [],
    }
    values.update(overrides)
    return values


class PersistencePolicyTests(unittest.TestCase):
    def test_01_discovery_only_required_edit_is_premature_stop(self):
        self.assertTrue(classify_premature_stop(**evidence()))

    def test_02_premature_stop_allows_exactly_one_retry(self):
        self.assertTrue(should_retry("PREMATURE_STOP", 1, 2))
        self.assertFalse(should_retry("PREMATURE_STOP", 2, 2))

    def test_03_second_premature_stop_is_final_acceptance_failure(self):
        self.assertTrue(classify_premature_stop(**evidence()))
        final_reason = "FAIL_ACCEPTANCE"
        self.assertFalse(should_retry(final_reason, 2, 2))

    def test_04_scope_violation_never_retries(self):
        self.assertFalse(classify_premature_stop(**evidence(violations=["other.txt"])))
        self.assertFalse(should_retry("FAIL_SCOPE", 1, 2))

    def test_05_successful_first_attempt_never_retries(self):
        self.assertFalse(classify_premature_stop(**evidence(changes=["target.py"], acceptance=[{"passed": True}], tool_names=["read", "edit", "bash"])))
        self.assertFalse(should_retry("PASS", 1, 2))

    def test_06_no_tool_early_exit_is_premature_stop(self):
        self.assertTrue(classify_premature_stop(**evidence(tool_names=[])))

    def test_07_retry_prompt_retains_complete_work_order(self):
        root = Path(r"D:\Josie")
        objective = "Seal fields: principal_id; Ring fields: allowed_paths; Scroll fields: job_id"
        order = WorkOrder.validate({
            "schema_version": "1", "job_id": "prompt-fidelity", "objective": objective,
            "first_action": "Inspect whether dbot/contracts.py exists, then create/update it.",
            "workspace": str(root), "harness": "mock", "model": "mock/exact",
            "allowed_changed_paths": ["dbot/contracts.py"], "timeout_seconds": 120,
            "max_attempts": 2, "acceptance": [{"type": "command", "argv": ["python", "-m", "py_compile", "dbot/contracts.py"]}],
            "prompt_profile": "test", "receipt_destination": str(root / "data/private/supervisor-local-code"),
            "requires_modification": True,
        })
        prompt = compile_prompt(order, retry=True)
        self.assertIn(objective, prompt)
        self.assertIn("dbot/contracts.py", prompt)
        self.assertIn("python -m py_compile dbot/contracts.py", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)

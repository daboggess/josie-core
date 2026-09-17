import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supervisor.remote_adapter import (
    delegate_supervised_local_code,
    parse_remote_job,
    supervised_local_code_status,
)
from supervisor.prompt_compiler import compile_prompt
from supervisor.verifier import run_acceptance
from supervisor.work_order import WorkOrder


class RemoteBridgeTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parent.parent / "data" / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "repo"
        self.workspace.mkdir()
        self.root = self.base / "josie"
        self.root.mkdir()
        self.request = "\n".join((
            f"Workspace: {self.workspace}", "Task:", "Modify result.txt.",
            "Allowed changes:", "result.txt", "Acceptance:",
            "command: D:\\Josie\\.venv\\Scripts\\python.exe -c pass",
        ))

    def tearDown(self):
        self.temp.cleanup()

    def test_bounded_request_compiles_supervisor_work_order(self):
        retrieval = {
            "triggered": True,
            "reason": "retrieval_triggered",
            "knowledge_state": "RETRIEVED",
            "packet": "bounded packet",
            "evidence": [{"source": "result.txt implementation detail"}],
        }
        order, path = parse_remote_job(
            self.request, request_id="bridge-test-0001", project_root=self.root,
            retrieval_context=retrieval)
        self.assertEqual(order["agent"], "josie-coder")
        self.assertEqual(order["harness"], "coder")
        self.assertEqual(order["model"], "josie-qual-ornith-1.5-9b-q6")
        self.assertEqual(order["context_limit"], 8192)
        self.assertTrue(order["primary_harness_executable"].endswith("goose.exe"))
        self.assertTrue(order["fallback_harness_executable"].endswith("opencode.exe"))
        self.assertEqual(order["side_effect_capabilities"], [])
        self.assertEqual(order["retrieved_evidence"], [{"source": "result.txt implementation detail"}])
        self.assertEqual(order["retrieval_summary"]["evidence_count"], 1)
        self.assertEqual(order["retrieval_summary"]["packet_chars"], len("bounded packet"))
        self.assertTrue(path.is_file())

    def test_acceptance_stops_before_trailing_orchestration(self):
        request = self.request + "\nComplete the work autonomously.\nReturn the normal receipt.\nStop when complete."
        order, _ = parse_remote_job(
            request, request_id="bridge-boundary-0006", project_root=self.root)
        self.assertEqual(order["acceptance"][0]["argv"], [
            "D:\\Josie\\.venv\\Scripts\\python.exe", "-c", "pass"])
        prompt = compile_prompt(WorkOrder.validate(order))
        acceptance = prompt.split("ACCEPTANCE\n", 1)[1].split("\n\nRECEIPTS", 1)[0]
        self.assertEqual(acceptance, "D:\\Josie\\.venv\\Scripts\\python.exe -c pass")
        self.assertIn("FINAL REPORT\nComplete the work autonomously.", prompt)

    def test_final_report_heading_cannot_become_acceptance_argv(self):
        request = self.request + "\nFINAL REPORT:\nSTATUS: PASS\nReport changed files and stop."
        order, _ = parse_remote_job(
            request, request_id="bridge-boundary-0009", project_root=self.root)
        self.assertEqual(order["acceptance"][0]["argv"], [
            "D:\\Josie\\.venv\\Scripts\\python.exe", "-c", "pass"])
        self.assertNotIn("FINAL", order["acceptance"][0]["argv"])
        self.assertNotIn("STATUS:", order["acceptance"][0]["argv"])

    def test_multiline_acceptance_is_rejected_not_reinterpreted(self):
        request = self.request + "\npython -m unittest\n"
        with self.assertRaisesRegex(ValueError, "exactly one command line"):
            parse_remote_job(
                request, request_id="bridge-boundary-0010", project_root=self.root)

    def test_supervisor_executes_only_structured_acceptance_argv(self):
        request = self.request + "\nFINAL REPORT:\nReport results and stop."
        order, _ = parse_remote_job(
            request, request_id="bridge-exec-argv-0011", project_root=self.root)
        validated = WorkOrder.validate(order)
        with patch("supervisor.verifier.subprocess.run") as execute_command:
            execute_command.return_value.returncode = 0
            execute_command.return_value.stdout = ""
            execute_command.return_value.stderr = ""
            results = run_acceptance(validated, [])
        self.assertTrue(results[0]["passed"])
        self.assertEqual(execute_command.call_args.args[0], [
            "D:\\Josie\\.venv\\Scripts\\python.exe", "-c", "pass"])

    def test_self_contained_task_excludes_irrelevant_history(self):
        retrieval = {"triggered": True, "packet": "old GPU conversation", "evidence": [
            {"evidence_id": "history:gpu", "excerpt": "We discussed buying an RTX GPU."}]}
        order, _ = parse_remote_job(
            self.request, request_id="bridge-retrieval-0007", project_root=self.root,
            retrieval_context=retrieval)
        self.assertEqual(order["retrieved_evidence"], [])
        self.assertEqual(order["retrieval_summary"]["evidence_count"], 0)
        self.assertEqual(order["retrieval_summary"]["candidate_evidence_count"], 1)

    def test_relevant_retrieval_and_write_scope_are_preserved(self):
        retrieval = {"triggered": True, "packet": "result format", "evidence": [
            {"evidence_id": "spec:result", "excerpt": "result.txt requires UTF-8 encoding"}]}
        order, _ = parse_remote_job(
            self.request, request_id="bridge-retrieval-0008", project_root=self.root,
            retrieval_context=retrieval)
        prompt = compile_prompt(WorkOrder.validate(order))
        self.assertEqual(order["retrieval_summary"]["evidence_count"], 1)
        self.assertIn("result.txt requires UTF-8 encoding", prompt)
        self.assertIn("Protected/read-only areas", prompt)
        self.assertIn("Allowed writes", prompt)
        self.assertIn("result.txt", prompt)
        self.assertIn("not invitations to ask what to do", prompt)
        self.assertIn("Report BLOCKED only for a real missing dependency", prompt)
        self.assertNotIn("result.txt\nProtected/read-only:\nresult.txt", prompt)

    def test_missing_scope_does_not_launch(self):
        incomplete = f"Workspace: {self.workspace}\nTask: inspect"
        with patch("supervisor.remote_adapter.execute") as launch:
            result = delegate_supervised_local_code(incomplete, "", request_id="bridge-test-0002", project_root=self.root)
        launch.assert_not_called()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "NEEDS_JOB_DETAILS")
        status = supervised_local_code_status(self.root, "bridge-test-0002")
        self.assertEqual(status["reason"], "NEEDS_JOB_DETAILS")

    def test_field_validation_failure_is_durably_queryable(self):
        request = "\n".join((
            "Task:", "Create a utility.", f"Workspace: {self.workspace}",
            "Allowed changes:", "Create and modify files only inside:",
            str(self.workspace / "created"), "Acceptance:", "1. Tests pass.",
        ))
        with patch("supervisor.remote_adapter.execute") as launch:
            result = delegate_supervised_local_code(
                request, "", request_id="bridge-field-failure-0003",
                project_root=self.root)
        launch.assert_not_called()
        self.assertEqual(result["reason"], "VALIDATION_FAIL")
        status = supervised_local_code_status(self.root, "bridge-field-failure-0003")
        self.assertEqual(status["reason"], "VALIDATION_FAIL")
        receipt = json.loads(Path(status["receipt"]).read_text(encoding="utf-8"))
        self.assertFalse(receipt["worker_launched"])
        self.assertEqual(receipt["harness_version"], "NOT_RUN")

    def test_persisted_work_order_is_accepted_not_not_found(self):
        order_dir = self.root / "data" / "private" / "supervisor-work-orders"
        order_dir.mkdir(parents=True)
        path = order_dir / "bridge-accepted-0004.json"
        path.write_text("{}", encoding="utf-8")
        result = supervised_local_code_status(self.root, "bridge-accepted-0004")
        self.assertEqual(result["status"], "accepted")
        self.assertIn("not yet evidenced", result["assistant_message"])

    def test_exception_after_persistence_gets_failure_receipt(self):
        with patch("supervisor.remote_adapter.execute", side_effect=ValueError("boom")):
            result = delegate_supervised_local_code(
                self.request, "", request_id="bridge-submit-error-0005",
                project_root=self.root)
        self.assertEqual(result["reason"], "SUPERVISOR_ERROR")
        status = supervised_local_code_status(self.root, "bridge-submit-error-0005")
        self.assertEqual(status["reason"], "SUPERVISOR_ERROR")
        receipt = json.loads(Path(status["receipt"]).read_text(encoding="utf-8"))
        self.assertIsNone(receipt["worker_launched"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

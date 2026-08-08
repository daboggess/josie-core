from __future__ import annotations

import tempfile
import unittest
import sqlite3
from contextlib import closing
from unittest.mock import patch
from pathlib import Path

from josie.config import load_config
from josie.tools import available_tools, run_tool
from josie.providers import probe_openai, provider_status
from josie.gui import respond
from josie.storage import LocalStore
from josie.diagnostics import (
    memory_export_snapshot, recovery_snapshot, restore_drill_snapshot, system_snapshot, uptime_snapshot,
)
from josie.reports import export_diagnostics, warning_snapshot
from josie.instance import gui_instance
from josie.roadmap import roadmap_summary
from josie.deployment import DeploymentController, _safe_private_serve
from josie.policy import load_policy, permission_for
from josie.provenance import INTERVIEW_QUESTIONS, origin_workflow_status
from josie.acceptance import acceptance_audit
from josie.jobs import JobRunner, available_job_handlers


class JosieTests(unittest.TestCase):
    @staticmethod
    def _write_policy(root: Path) -> None:
        config = root / "config"
        config.mkdir(exist_ok=True)
        (config / "permissions.json").write_text(
            '{"schema_version":1,"default":"forbidden",'
            '"autonomous":["run_tests"],'
            '"approval_required":["install_software"],'
            '"forbidden":["bypass_security"]}', encoding="utf-8"
        )

    def test_machine_policy_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_policy(root)
            self.assertEqual(permission_for("run tests", root)["decision"], "autonomous")
            self.assertEqual(permission_for("install software", root)["decision"], "approval_required")
            self.assertEqual(permission_for("unknown future power", root)["decision"], "forbidden")

    def test_machine_policy_rejects_overlap_and_permissive_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            config.mkdir()
            path = config / "permissions.json"
            path.write_text(
                '{"default":"autonomous","autonomous":[],"approval_required":[],"forbidden":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "default"):
                load_policy(root)
            path.write_text(
                '{"default":"forbidden","autonomous":["x"],'
                '"approval_required":["x"],"forbidden":[]}', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "multiple"):
                load_policy(root)
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

    def test_upgrade_fund_separates_actuals_from_estimates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            store.record_ledger_entry(
                basis="actual", category="revenue", amount="25.00", description="paid work"
            )
            store.record_ledger_entry(
                basis="actual", category="api_cost", amount="2.50", description="provider invoice"
            )
            store.record_ledger_entry(
                basis="estimated", category="savings", amount="100.00", description="time estimate"
            )
            summary = store.ledger_summary()
            self.assertEqual(summary["actual_balance_cents"], 2250)
            self.assertEqual(summary["estimated_savings_cents"], 10000)
            self.assertNotEqual(summary["actual_balance_cents"], 12250)
            answer = respond("ledger", config=load_config(root / ".env"), project_root=root, store=store)
            self.assertIn("balance $22.50", answer)
            self.assertIn("not earned money", answer)
            self.assertIn("cannot spend", answer)

    def test_upgrade_fund_rejects_actual_savings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = LocalStore(Path(directory) / "data" / "josie.db")
            with self.assertRaisesRegex(ValueError, "estimated"):
                store.record_ledger_entry(
                    basis="actual", category="savings", amount="10", description="not cash"
                )

    def test_gui_records_ledger_fact_without_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            result = respond(
                "record estimated savings $15.25 for local processing",
                config=load_config(root / ".env"), project_root=root, store=store,
            )
            self.assertIn("no transaction occurred", result.lower())
            self.assertEqual(store.ledger_summary()["estimated_savings_cents"], 1525)

    def test_origin_records_start_unverified_and_require_explicit_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            record_id = store.record_provenance(source="Bernie", statement="A suggested design")
            self.assertEqual(store.provenance_records()[0][3], "unverified")
            self.assertTrue(store.decide_provenance(record_id, "confirmed"))
            self.assertEqual(store.provenance_records()[0][3], "confirmed")
            self.assertFalse(store.decide_provenance(record_id, "rejected"))

    def test_origin_gui_does_not_contact_cloud_or_auto_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "ORIGIN_AND_PROVENANCE.md").write_text("workflow", encoding="utf-8")
            store = LocalStore(root / "data" / "josie.db")
            config = load_config(root / ".env")
            answer = respond(
                "record origin from Sophie: Josie should be cautious",
                config=config, project_root=root, store=store,
            )
            self.assertIn("unverified", answer)
            self.assertEqual(store.provenance_records()[0][3], "unverified")
            workflow = origin_workflow_status(root)
            self.assertFalse(workflow["cloud_activity"])
            self.assertFalse(workflow["automatic_import"])
            self.assertEqual(workflow["question_count"], len(INTERVIEW_QUESTIONS))

    def test_acceptance_audit_distinguishes_human_gates_from_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".venv" / "Scripts").mkdir(parents=True)
            (root / ".venv" / "Scripts" / "python.exe").touch()
            (root / "config").mkdir()
            (root / "config" / "permissions.json").write_text(
                '{"default":"forbidden","autonomous":[],"approval_required":[],"forbidden":[]}',
                encoding="utf-8",
            )
            (root / "config" / "deployment.json").write_text(
                '{"schema_version":1,"components":[]}', encoding="utf-8"
            )
            (root / "deploy").mkdir()
            (root / "deploy" / "compose.yaml").write_text(
                'ports:\n- "127.0.0.1:5678:5678"\n- "127.0.0.1:3000:8080"\n- "127.0.0.1:3010:3010"\n',
                encoding="utf-8",
            )
            LocalStore(root / "data" / "josie.db").create_daily_backup(root / "data" / "backups")
            result = acceptance_audit(config=load_config(root / ".env"), project_root=root)
            self.assertFalse(result["audit_mutated_machine"])
            self.assertFalse(result["arbitrary_shell_available"])
            self.assertGreater(result["counts"]["human_gate"], 0)
            self.assertGreater(result["counts"]["failed"], 0)

    def test_attended_gate_preserves_security_boundaries(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        script = (project_root / "scripts" / "Invoke-JosieSystemGate.ps1").read_text(encoding="utf-8")
        lowered = script.lower()
        self.assertIn("get-authenticodesignature", lowered)
        self.assertIn("--no-distribution", lowered)
        self.assertIn("--user", lowered)
        self.assertIn("--no-windows-containers", lowered)
        self.assertNotIn("enablelua", lowered)
        self.assertNotIn("autoadminlogon", lowered)
        self.assertNotIn("new-netfirewallrule", lowered)
        self.assertNotIn("tailscale up", lowered)
        self.assertNotIn("--accept-license", lowered)
        self.assertNotIn("set-executionpolicy", lowered)

    def test_service_gate_requires_immutable_images_and_local_preflight(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        script = (project_root / "scripts" / "Invoke-JosieServiceGate.ps1").read_text(encoding="utf-8")
        lowered = script.lower()
        self.assertIn("sha256", lowered)
        self.assertIn("services-preflight", lowered)
        self.assertIn("$dockerpath compose", lowered)
        self.assertIn("d:\\josie-storage", lowered)
        self.assertNotIn("--volumes", lowered)
        self.assertNotIn("tailscale up", lowered)
        self.assertNotIn("0.0.0.0:", lowered)
        self.assertNotIn("set-executionpolicy", lowered)

    def test_job_runner_only_executes_registered_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            runner = JobRunner(config=load_config(root / ".env"), project_root=root, store=store)
            self.assertIn("health_check", available_job_handlers())
            with self.assertRaisesRegex(ValueError, "not allowed"):
                runner.queue("shell", {"command": "whoami"})
            job_id = runner.queue("health_check")
            result = runner.run_one()
            self.assertEqual(result["job_id"], job_id)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(store.job_summary()["succeeded"], 1)

    def test_job_failures_retry_at_most_three_times_and_never_execute_repairs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            runner = JobRunner(config=load_config(root / ".env"), project_root=root, store=store)
            job_id = runner.queue("health_check", {"unexpected": True}, max_attempts=3)
            first = runner.run_one()
            second = runner.run_one()
            third = runner.run_one()
            self.assertEqual(first["status"], "pending")
            self.assertEqual(second["status"], "pending")
            self.assertEqual(third["status"], "review_required")
            self.assertFalse(third["generated_code_executed"])
            self.assertEqual(third["job_id"], job_id)
            self.assertEqual(store.job_summary()["review_required"], 1)
            self.assertEqual(runner.run_one()["status"], "idle")

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
        self.assertIn("memory-export", available_tools())
        self.assertIn("restore-drill", available_tools())

    def test_memory_export_is_local_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("OPENAI_API_KEY=never-export-this\n", encoding="utf-8")
            store = LocalStore(root / "data" / "josie.db")
            store.remember("governed memory")
            store.add_task("governed task")
            result = memory_export_snapshot(config=load_config(root / ".env"), project_root=root)
            exported = Path(str(result["path"])).read_text(encoding="utf-8")
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["cloud_activity"])
            self.assertIn("governed memory", exported)
            self.assertNotIn("never-export-this", exported)

    def test_restore_drill_never_changes_live_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = LocalStore(root / "data" / "josie.db")
            store.remember("before backup")
            store.create_daily_backup(root / "data" / "backups")
            store.remember("after backup")
            result = restore_drill_snapshot(config=load_config(root / ".env"), project_root=root)
            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["live_database_changed"])
            self.assertEqual(result["record_counts"]["memories"], 1)
            self.assertEqual(len(store.memories()), 2)

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

    def test_deployment_state_is_idempotent_and_spend_locked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "deployment.json").write_text(
                '{"schema_version":1,"components":[{"id":"wsl","phase":"system","gate":"admin_and_reboot"}]}',
                encoding="utf-8",
            )
            config = load_config(root / ".env")
            controller = DeploymentController(config=config, project_root=root)
            status = controller.status()
            self.assertFalse(status["cloud_calls_allowed"])
            self.assertEqual(status["pending_human_gates"][0]["id"], "wsl")

    def test_service_preflight_rejects_unverified_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "deployment.json").write_text(
                '{"schema_version":1,"components":[]}', encoding="utf-8"
            )
            deploy = root / "deploy"
            deploy.mkdir()
            (deploy / "compose.yaml").write_text(
                'ports:\n- "127.0.0.1:5678:5678"\n- "127.0.0.1:3000:8080"\n- "127.0.0.1:3010:3010"\n',
                encoding="utf-8",
            )
            (deploy / ".env.services").write_text(
                "N8N_IMAGE=n8nio/n8n:latest\n"
                "OPEN_WEBUI_IMAGE=open-webui:main\n"
                "PLAYWRIGHT_IMAGE=playwright:latest\n",
                encoding="utf-8",
            )
            result = DeploymentController(
                config=load_config(root / ".env"), project_root=root
            ).service_preflight()
            self.assertEqual(result["status"], "waiting")
            self.assertFalse(result["network_activity"])
            self.assertFalse(result["services_started"])
            self.assertEqual(len(result["issues"]), 3)

    def test_service_preflight_rejects_unsafe_compose_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "deployment.json").write_text(
                '{"schema_version":1,"components":[]}', encoding="utf-8"
            )
            deploy = root / "deploy"
            deploy.mkdir()
            (deploy / "compose.yaml").write_text(
                "privileged: true\nvolumes:\n- /var/run/docker.sock:/var/run/docker.sock\n",
                encoding="utf-8",
            )
            result = DeploymentController(
                config=load_config(root / ".env"), project_root=root
            ).service_preflight()
            self.assertEqual(result["status"], "waiting")
            self.assertTrue(any("docker.sock" in issue for issue in result["issues"]))

    def test_runtime_validation_requires_locked_browser(self) -> None:
        class FakeResponse:
            def __init__(self, body: str) -> None:
                self.status = 200
                self._body = body.encode()
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self, _limit: int) -> bytes:
                return self._body

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "deployment.json").write_text(
                '{"schema_version":1,"components":[]}', encoding="utf-8"
            )
            controller = DeploymentController(config=load_config(root / ".env"), project_root=root)
            def locked_response(request, timeout=0):
                del timeout
                url = request if isinstance(request, str) else request.full_url
                return FakeResponse('{"execution":false,"allowedHosts":0}' if url.endswith("3010/health") else '{"status":true}')
            with patch("josie.deployment.urllib.request.urlopen", side_effect=locked_response):
                self.assertEqual(controller.service_runtime_status()["status"], "ready")
            def unlocked_response(request, timeout=0):
                del timeout
                url = request if isinstance(request, str) else request.full_url
                return FakeResponse('{"execution":true,"allowedHosts":1}' if url.endswith("3010/health") else '{"status":true}')
            with patch("josie.deployment.urllib.request.urlopen", side_effect=unlocked_response):
                result = controller.service_runtime_status()
                self.assertEqual(result["status"], "waiting")
                self.assertFalse(result["browser_execution_locked"])

    def test_tailscale_serve_policy_allows_only_private_open_webui(self) -> None:
        safe = (
            "https://refurb.example.ts.net (tailnet only)\n"
            "|-- / proxy http://127.0.0.1:3000"
        )
        self.assertTrue(_safe_private_serve(safe))
        self.assertFalse(_safe_private_serve(safe.replace("tailnet only", "Funnel on")))
        self.assertFalse(_safe_private_serve(safe + "\nproxy http://127.0.0.1:5678"))
        self.assertFalse(_safe_private_serve(safe + "\nproxy http://127.0.0.1:3010"))

    def test_service_backup_is_read_only_verified_and_non_deleting(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        script = (project_root / "scripts" / "Backup-JosieServices.ps1").read_text(encoding="utf-8").lower()
        self.assertIn("josie_n8n_data:/source:ro", script)
        self.assertIn("josie_open_webui_data:/source:ro", script)
        self.assertIn("get-filehash", script)
        self.assertIn("tar.exe -tzf", script)
        self.assertIn("finally", script)
        self.assertNotIn("volume rm", script)
        self.assertNotIn("remove-item", script)
        self.assertNotIn("--volumes", script)


if __name__ == "__main__":
    unittest.main()

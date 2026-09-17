from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from josie.config import load_config
from josie.storage import LocalStore
from josie.conversation_control import _handler_class
from mission_manager.dbot_adaptation import FAILED_RECEIPT_ID, apply_authorized_decomposition
from mission_manager.dispatcher import DispatchError, MissionManager
from mission_manager.ingress import _public, continue_mission, mission_status, submit_mission
from supervisor.receipts import write_receipt
from tests.test_mission_manager import Harness, ROOT, TMP, plan


class NoReceiptHarness:
    calls = 0

    def __call__(self, order_path: Path):
        self.calls += 1
        order = json.loads(order_path.read_text(encoding="utf-8"))
        return {"supervisor_version": "test", "job_id": order["job_id"],
                "final_status": "PASS", "reason": "PASS"}, None


class FailedDbotHarness:
    def __init__(self, receipt_directory: Path):
        self.receipt_directory = receipt_directory

    def __call__(self, order_path: Path):
        order = json.loads(order_path.read_text(encoding="utf-8"))
        receipt = {
            "schema_version": "1", "supervisor_version": "test", "job_id": order["job_id"],
            "attempt": 1, "requested_model": order["model"], "elapsed_seconds": 120.187,
            "timed_out": True, "worker_changed_paths": [], "scope_violations": [],
            "acceptance_results": [{"passed": False}], "tool_activity": [],
            "final_status": "FAIL", "reason": "FAIL_TIMEOUT",
        }
        path = write_receipt(self.receipt_directory, receipt, receipt_id=FAILED_RECEIPT_ID)
        return receipt, path


class MissionFrontDoorTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=TMP)
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def manager(self, harness=None):
        return MissionManager(self.base / "data/private/missions",
                              receipt_directory=self.base / "data/private/supervisor-local-code",
                              work_order_directory=self.base / "data/private/supervisor-work-orders",
                              supervisor_execute=harness)

    def load_filter(self):
        source = ROOT / "deploy/open-webui/exact-tool-response-filter.py"
        spec = importlib.util.spec_from_file_location("mission_filter_test", source)
        module = importlib.util.module_from_spec(spec)
        stub = types.ModuleType("pydantic")
        stub.BaseModel = object
        stub.Field = lambda default=None, **kwargs: default
        with patch.dict("sys.modules", {"pydantic": stub}):
            spec.loader.exec_module(module)
        return module

    def test_01_continue_mission_parses_valid_id(self):
        module = self.load_filter()
        self.assertEqual(("continue", "dbot-seed-v0", None), module._mission_directive("Continue Mission: dbot-seed-v0"))

    def test_01b_explicit_fallback_parses_and_reaches_control_plane(self):
        module = self.load_filter()
        command = "Continue Mission: dbot-seed-v0\nFallback Worker: gemma4:12b"
        self.assertEqual(("continue", "dbot-seed-v0", "gemma4:12b"),
                         module._mission_directive(command))
        response = {"schema_version": 1, "mission_id": "dbot-seed-v0",
                    "mission_status": "FAILED", "stop_reason": "FAIL_ACCEPTANCE",
                    "progress": {"completed": 0, "total": 6},
                    "jobs_dispatched": ["job-1a-contract-structures"],
                    "jobs_not_run": [], "supervisor_invoked": True,
                    "assistant_message": "JOSIE MISSION MANAGER — ACTUAL RESULT"}
        body = {"model": "qwen3:14b", "chat_id": "fallback-test", "messages": [
            {"role": "user", "content": command}, {"role": "assistant", "content": "draft"}]}
        with patch.object(module, "_record_history"), patch.object(
                module, "_control_post", return_value=response) as control:
            inlet = module.Filter().inlet(body)
        self.assertEqual("/v1/missions/continue", control.call_args.args[0])
        self.assertEqual("gemma4:12b", control.call_args.args[1]["fallback_worker"])
        self.assertEqual(1, inlet["max_tokens"])

    def test_02_malformed_command_rejected_without_control_call(self):
        module = self.load_filter()
        body = {"model": "qwen3:14b", "messages": [
            {"role": "user", "content": "Continue Mission: ../bad"}, {"role": "assistant", "content": "draft"}]}
        with patch.object(module, "_record_history"), patch.object(module, "_control_post") as control:
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))
        control.assert_not_called()
        self.assertIn("INVALID_MISSION_ID", result["messages"][-1]["content"])

    def test_03_missing_mission_is_deterministic(self):
        result = continue_mission("missing-mission", project_root=self.base)
        self.assertEqual("NEEDS_MISSION", result["reason"])
        self.assertIn("Mission not found", result["assistant_message"])

    def test_04_explicit_mission_bypasses_qwen_tool_routing(self):
        module = self.load_filter()
        response = {"schema_version": 1, "mission_id": "dbot-seed-v0", "mission_status": "BLOCKED",
                    "stop_reason": "FAIL_TIMEOUT", "progress": {"completed": 0, "total": 6},
                    "jobs_dispatched": ["job-1a"], "jobs_not_run": ["job-1b"],
                    "supervisor_invoked": True, "assistant_message": "JOSIE MISSION MANAGER — ACTUAL RESULT\nMission status: BLOCKED"}
        body = {"model": "qwen3:14b", "chat_id": "phone", "messages": [
            {"role": "user", "content": "Continue Mission: dbot-seed-v0"}, {"role": "assistant", "content": "qwen draft"}],
            "tool_ids": ["server:josie-subscription-seats/continue_mission"]}
        with patch.object(module, "_record_history"), patch.object(module, "_control_post", return_value=response) as control:
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))
        self.assertEqual([], inlet["tool_ids"])
        self.assertTrue(inlet["stream"])
        self.assertEqual(1, inlet["max_tokens"])
        self.assertIsNone(module.Filter().stream({"draft": True}, __body__=inlet))
        self.assertEqual(response["assistant_message"], result["messages"][-1]["content"])
        self.assertEqual("/v1/missions/continue", control.call_args.args[0])

    def test_05_ordinary_chat_remains_unchanged(self):
        module = self.load_filter()
        body = {"model": "qwen3:14b", "messages": [
            {"role": "user", "content": "Hello Josie"}, {"role": "assistant", "content": "Hello Dustin"}]}
        with patch.object(module, "_control_post") as control:
            result = asyncio.run(module.Filter().outlet(body))
        control.assert_not_called()
        self.assertEqual("Hello Dustin", result["messages"][-1]["content"])

    def test_06_delegate_local_route_is_unchanged(self):
        module = self.load_filter()
        response = {"assistant_message": "JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: PASS"}
        body = {"model": "qwen3:14b", "chat_id": "local", "messages": [
            {"role": "user", "content": "Delegate Local: inspect"}, {"role": "assistant", "content": "draft"}]}
        with patch.object(module, "_record_history"), patch.object(module, "_control_post", return_value=response) as control:
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))
        self.assertEqual("/v1/delegate/local-code", control.call_args.args[0])
        self.assertTrue(result["messages"][-1]["content"].startswith("JOSIE LOCAL CODE"))

    def test_07_only_ready_job_dispatches_and_pass_unlocks_next(self):
        manager = self.manager(Harness(self.base))
        manager.create(plan(dependencies=True))
        mission = manager.dispatch_next("test-mission")
        self.assertEqual(["PASS", "READY"], [job["status"] for job in mission["jobs"]])
        self.assertEqual([1, 0], [job["attempts"] for job in mission["jobs"]])

    def test_08_blocked_job_cannot_dispatch(self):
        manager = self.manager(Harness(self.base, "FAIL", "FAIL_ACCEPTANCE"))
        manager.create(plan(dependencies=True))
        manager.dispatch_next("test-mission")
        with self.assertRaises(DispatchError):
            manager.dispatch_next("test-mission")

    def test_09_supervisor_no_receipt_stops_without_pass_or_bypass(self):
        harness = NoReceiptHarness()
        manager = self.manager(harness)
        manager.create(plan())
        outcome = manager.continue_until_stop("test-mission")
        self.assertEqual("SUPERVISOR_FAILURE", outcome["stop_reason"])
        self.assertEqual("BLOCKED", outcome["mission"]["jobs"][0]["status"])
        self.assertIsNone(outcome["mission"]["jobs"][0]["receipt_ref"])
        self.assertEqual(1, harness.calls)

    def test_10_continue_persists_each_pass_and_completes(self):
        manager = self.manager(Harness(self.base))
        manager.create(plan(dependencies=True))
        outcome = manager.continue_until_stop("test-mission")
        self.assertEqual("COMPLETE", outcome["mission"]["status"])
        self.assertEqual(["job-1", "job-2"], outcome["dispatched"])
        reloaded = manager.load("test-mission")
        self.assertEqual(2, len(reloaded["receipt_refs"]))
        events = manager.store.events_path("test-mission").read_text(encoding="utf-8")
        self.assertEqual(2, events.count('"event": "RECEIPT_CONSUMED"'))

    def test_11_not_run_is_never_reported_as_dispatched(self):
        manager = self.manager()
        mission = manager.create(plan(dependencies=True))
        result = _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
        self.assertEqual([], result["jobs_dispatched"])
        self.assertEqual(["job-1", "job-2"], result["jobs_not_run"])
        self.assertNotIn("Jobs dispatched this request: job-1", result["assistant_message"])

    def test_12_status_is_read_only_and_does_not_invoke_supervisor(self):
        manager = self.manager()
        manager.create(plan())
        with patch("mission_manager.ingress.MissionManager") as manager_type:
            manager_type.return_value.load.return_value = manager.load("test-mission")
            result = mission_status("test-mission", project_root=self.base)
            manager_type.return_value.continue_until_stop.assert_not_called()
        self.assertEqual("STATUS_ONLY", result["stop_reason"])

    def test_13_authorized_decomposition_is_idempotent_and_preserves_failure(self):
        source_plan = json.loads((ROOT / "mission_manager/plans/dbot_seed_v0.json").read_text(encoding="utf-8"))
        manager = self.manager(FailedDbotHarness(self.base / "data/private/supervisor-local-code"))
        manager.create(source_plan)
        manager.dispatch_next("dbot-seed-v0")
        adapted, changed = apply_authorized_decomposition(manager)
        again, duplicate = apply_authorized_decomposition(manager)
        old = next(job for job in adapted["jobs"] if job["job_id"] == "job-1-contracts")
        self.assertTrue(changed)
        self.assertFalse(duplicate)
        self.assertEqual("SUPERSEDED_BY_DECOMPOSITION", old["result_reason"])
        self.assertEqual(1, len(again["applied_adaptations"]))
        self.assertEqual(FAILED_RECEIPT_ID, old["receipt_evidence"]["receipt_id"])

    def test_14_submit_mission_directive_detection(self):
        module = self.load_filter()
        sample = plan()
        valid_cmd = f"Submit Mission:\n{json.dumps(sample, indent=2)}"
        self.assertEqual(("submit", sample, None), module._mission_directive(valid_cmd))
        self.assertEqual(("malformed_json", None, None), module._mission_directive("Submit Mission:\n{bad-json"))
        self.assertEqual(("malformed_json", None, None), module._mission_directive("Submit Mission:"))
        self.assertEqual(("malformed_json", None, None), module._mission_directive("Submit Mission:   \n  "))
        self.assertEqual(("invalid_plan", None, None), module._mission_directive("Submit Mission:\n[1, 2]"))
        self.assertIsNone(module._mission_directive("Please do not Submit Mission: now"))
        self.assertIsNone(module._mission_directive("Tell me about Submit Mission:"))

    def test_15_submit_mission_reaches_control_plane_and_bypasses_qwen_tool_routing(self):
        module = self.load_filter()
        sample = plan()
        cmd = f"Submit Mission:\n{json.dumps(sample)}"
        response = {
            "schema_version": 1,
            "mission_id": sample["mission_id"],
            "mission_status": "PLANNED",
            "stop_reason": "SUBMITTED",
            "progress": {"completed": 0, "total": 1},
            "jobs_dispatched": [],
            "jobs_not_run": ["job-1"],
            "supervisor_invoked": False,
            "assistant_message": "JOSIE MISSION MANAGER — ACTUAL RESULT\nMission status: PLANNED\nStop reason: SUBMITTED",
        }
        body = {
            "model": "qwen3:14b",
            "chat_id": "phone-submit",
            "messages": [
                {"role": "user", "content": cmd},
                {"role": "assistant", "content": "qwen draft"},
            ],
            "tool_ids": ["server:josie-subscription-seats/submit_mission"],
        }
        with patch.object(module, "_record_history"), patch.object(
            module, "_control_post", return_value=response
        ) as control:
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))

        self.assertEqual([], inlet["tool_ids"])
        self.assertTrue(inlet["stream"])
        self.assertEqual(1, inlet["max_tokens"])
        self.assertIsNone(module.Filter().stream({"draft": True}, __body__=inlet))
        self.assertEqual(response["assistant_message"], result["messages"][-1]["content"])
        self.assertEqual("/v1/missions/submit", control.call_args.args[0])
        self.assertEqual(sample, control.call_args.args[1]["plan"])

    def test_16_submit_malformed_json_rejected_without_control_call(self):
        module = self.load_filter()
        body = {
            "model": "qwen3:14b",
            "messages": [
                {"role": "user", "content": "Submit Mission:\n{not valid json"},
                {"role": "assistant", "content": "draft"},
            ],
        }
        with patch.object(module, "_record_history"), patch.object(module, "_control_post") as control:
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))
        control.assert_not_called()
        self.assertIn("MALFORMED_JSON", result["messages"][-1]["content"])

    def test_17_submit_invalid_plan_rejected_without_supervisor_invocation(self):
        bad_plan = {"mission_id": "bad-plan-001", "missing_required_fields": True}
        result = submit_mission(bad_plan, project_root=self.base)
        self.assertEqual("rejected", result["status"])
        self.assertEqual("INVALID_PLAN", result["reason"])
        self.assertIn("REQUEST REJECTED", result["assistant_message"])
        mission_file = self.base / "data" / "private" / "missions" / "bad-plan-001.json"
        self.assertFalse(mission_file.exists())

    def test_18_submit_creates_durable_mission_queried_by_status_and_continued(self):
        sample = plan(dependencies=True)
        res = submit_mission(sample, project_root=self.base)
        self.assertEqual("PLANNED", res["mission_status"])
        self.assertEqual("SUBMITTED", res["stop_reason"])
        self.assertFalse(res["supervisor_invoked"])

        mission_file = self.base / "data" / "private" / "missions" / f"{sample['mission_id']}.json"
        self.assertTrue(mission_file.exists())

        # Status immediately queries it
        status = mission_status(sample["mission_id"], project_root=self.base)
        self.assertEqual("PLANNED", status["mission_status"])
        self.assertEqual("STATUS_ONLY", status["stop_reason"])
        self.assertFalse(status["supervisor_invoked"])

        # Continue dispatches and completes
        cont = continue_mission(
            sample["mission_id"], project_root=self.base, supervisor_execute=Harness(self.base)
        )
        self.assertEqual("COMPLETE", cont["mission_status"])
        self.assertEqual("COMPLETE", cont["stop_reason"])

    def test_19_duplicate_submit_does_not_duplicate_execution(self):
        sample = plan()
        res1 = submit_mission(sample, project_root=self.base)
        self.assertEqual("SUBMITTED", res1["stop_reason"])

        res2 = submit_mission(sample, project_root=self.base)
        self.assertEqual("ALREADY_EXISTS", res2["stop_reason"])
        self.assertEqual([], res2["jobs_dispatched"])
        self.assertFalse(res2["supervisor_invoked"])

    def test_20_http_endpoint_submit_creates_durable_mission_and_enforces_auth(self):
        (self.base / ".env").write_text("JOSIE_STAGE=dev\n")
        (self.base / "data").mkdir(parents=True, exist_ok=True)
        (self.base / "mission_manager" / "plans").mkdir(parents=True, exist_ok=True)
        store = LocalStore(self.base / "data" / "josie.db")
        config = load_config(self.base / ".env")
        token = "test-token-secret-12345"
        handler = _handler_class(
            project_root=self.base, config=config, store=store, token=token, port=0
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            sample = plan()

            # 1. Unauthenticated request rejected with 401
            req_unauth = urllib.request.Request(
                f"{base_url}/v1/missions/submit",
                data=json.dumps({"plan": sample}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_unauth)
            self.assertEqual(401, ctx.exception.code)

            # 2. Authenticated valid submission creates durable mission
            req_auth = urllib.request.Request(
                f"{base_url}/v1/missions/submit",
                data=json.dumps({"plan": sample}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_auth) as resp:
                self.assertEqual(200, resp.status)
                body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual("SUBMITTED", body["stop_reason"])
            self.assertEqual("PLANNED", body["mission_status"])
            self.assertFalse(body["supervisor_invoked"])
            self.assertTrue(
                (self.base / "data" / "private" / "missions" / f"{sample['mission_id']}.json").exists()
            )
            self.assertTrue(
                (self.base / "mission_manager" / "plans" / f"{sample['mission_id']}.json").exists()
            )

            # 3. Status queries the submitted mission
            req_status = urllib.request.Request(
                f"{base_url}/v1/missions/status",
                data=json.dumps({"mission_id": sample["mission_id"]}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_status) as resp:
                self.assertEqual(200, resp.status)
                st_body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual("STATUS_ONLY", st_body["stop_reason"])
            self.assertEqual("PLANNED", st_body["mission_status"])

            # 4. Duplicate submission is idempotent
            with urllib.request.urlopen(req_auth) as resp:
                self.assertEqual(200, resp.status)
                dup_body = json.loads(resp.read().decode("utf-8"))
            self.assertEqual("ALREADY_EXISTS", dup_body["stop_reason"])
            self.assertEqual([], dup_body["jobs_dispatched"])
        finally:
            server.shutdown()
            server.server_close()

    def test_21_invariant_a_nonexistent_mission_cannot_produce_success_or_pass(self):
        # 1. Direct ingress call for nonexistent mission
        res = mission_status("nonexistent-mission-004", project_root=self.base)
        self.assertEqual("not_found", res["status"])
        self.assertEqual("NEEDS_MISSION", res["reason"])
        for forbidden in ["SUCCESS", "COMPLETE", "PASS", "3/3"]:
            self.assertNotIn(forbidden, res["assistant_message"])
        self.assertIn("Mission not found", res["assistant_message"])

        # 2. Front-door filter directive call
        module = self.load_filter()
        body = {
            "model": "qwen3:14b",
            "messages": [
                {"role": "user", "content": "Mission Status: nonexistent-mission-004"},
                {"role": "assistant", "content": "draft"},
            ],
        }
        with patch.object(module, "_record_history"), patch.object(
            module, "_control_post", return_value=res
        ):
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))
        final_text = result["messages"][-1]["content"]
        for forbidden in ["SUCCESS", "COMPLETE", "PASS", "3/3"]:
            self.assertNotIn(forbidden, final_text)

        # 3. Freeform conversational query asking about nonexistent mission
        conv_body = {
            "model": "qwen3:14b",
            "messages": [
                {"role": "user", "content": "What is the status of nonexistent-mission-004?"},
                {"role": "assistant", "content": "JOSIE MISSION MANAGER — ACTUAL RESULT\nMission status: SUCCESS\nProgress: 3/3 complete"},
            ],
        }
        with patch.object(module, "_record_history"):
            conv_result = asyncio.run(module.Filter().outlet(conv_body))
        conv_text = conv_result["messages"][-1]["content"]
        self.assertEqual(
            "MISSION RESULT NOT VERIFIED\nReason: authoritative persisted mission evidence was not found.",
            conv_text,
        )
        for forbidden in ["SUCCESS", "COMPLETE", "PASS", "3/3"]:
            self.assertNotIn(forbidden, conv_text)

    def test_22_invariant_b_job_without_receipt_cannot_be_pass(self):
        manager = self.manager()
        sample = plan()
        mission = manager.create(sample)
        # Attempt to mark job as PASS without receipt
        mission["jobs"][0]["status"] = "PASS"
        mission["jobs"][0]["receipt_ref"] = None

        with self.assertRaises(ValueError) as ctx:
            _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
        self.assertIn("rejected PASS job without receipt", str(ctx.exception))

        # Test with missing receipt file on disk
        fake_receipt_path = str(self.base / "nonexistent-receipt.json")
        mission["jobs"][0]["receipt_ref"] = fake_receipt_path
        with self.assertRaises(ValueError) as ctx:
            _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
        self.assertIn("rejected missing receipt file", str(ctx.exception))

        # Test with receipt having final_status == FAIL
        fail_receipt = {
            "schema_version": "1", "supervisor_version": "test", "job_id": "job-1",
            "attempt": 1, "final_status": "FAIL", "reason": "FAIL_ACCEPTANCE",
            "acceptance_results": [{"passed": False}],
        }
        r_path = write_receipt(self.base / "data/private/supervisor-local-code", fail_receipt)
        mission["jobs"][0]["receipt_ref"] = str(r_path)
        with self.assertRaises(ValueError) as ctx:
            _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
        self.assertIn("rejected non-PASS receipt", str(ctx.exception))

        # When queried via mission_status on disk with invalid PASS state
        manager.store.save(mission)
        st = mission_status(sample["mission_id"], project_root=self.base)
        self.assertEqual("unverified", st["status"])
        self.assertEqual(
            "MISSION RESULT NOT VERIFIED\nReason: authoritative persisted mission evidence was not found.",
            st["assistant_message"],
        )

    def test_23_invariant_c_missing_artifacts_cannot_be_deliverable_claim(self):
        # Create a job with PASS receipt, but missing acceptance deliverable artifact
        sample = {
            "mission_id": "test-artifact-mission",
            "title": "Artifact Test",
            "objective": "Verify deliverable checks.",
            "jobs": [{
                "job_id": "job-1", "title": "First", "department": "coding",
                "objective": "Produce deliverable.", "dependencies": [],
                "workspace": str(self.base), "allowed_changes": ["reports/missing_artifact.md"],
                "acceptance": [{"type": "file_exists", "path": "reports/missing_artifact.md"}],
                "timeout": 120, "status": "PASS", "required": True, "attempts": 1,
                "dispatch_ids": ["job-1"],
            }],
        }
        # Receipt exists and claims PASS with machine acceptance True
        receipt = {
            "schema_version": "1", "supervisor_version": "test", "job_id": "job-1",
            "attempt": 1, "final_status": "PASS", "reason": "PASS",
            "acceptance_results": [{"type": "file_exists", "passed": True}],
        }
        r_path = write_receipt(self.base / "data/private/supervisor-local-code", receipt)
        sample["jobs"][0]["receipt_ref"] = str(r_path)
        sample["jobs"][0]["receipt_evidence"] = receipt
        sample["status"] = "COMPLETE"
        sample["progress"] = {"completed": 1, "total": 1, "percent": 100}

        # Deliverable file does NOT exist on disk
        artifact_path = self.base / "reports" / "missing_artifact.md"
        if artifact_path.exists():
            artifact_path.unlink()

        with self.assertRaises(ValueError) as ctx:
            _public(sample, dispatched=[], stop_reason="COMPLETE")
        self.assertIn("missing deliverable artifact: reports/missing_artifact.md", str(ctx.exception))

        # Now create the deliverable file on disk -> _public must succeed
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("actual deliverable content", encoding="utf-8")
        result = _public(sample, dispatched=[], stop_reason="COMPLETE")
        self.assertEqual("COMPLETE", result["mission_status"])

    def test_24_invariant_d_exact_machine_statuses_preserved(self):
        manager = self.manager()
        sample = plan()
        mission = manager.create(sample)

        # 1. PLANNED is preserved verbatim
        st_planned = _public(mission, dispatched=[], stop_reason="SUBMITTED")
        self.assertEqual("PLANNED", st_planned["mission_status"])
        self.assertIn("Mission status: PLANNED", st_planned["assistant_message"])
        self.assertNotIn("SUCCESS", st_planned["assistant_message"])

        # 2. Blocked status is preserved verbatim
        mission["status"] = "BLOCKED"
        st_blocked = _public(mission, dispatched=[], stop_reason="BLOCKED")
        self.assertEqual("BLOCKED", st_blocked["mission_status"])
        self.assertIn("Mission status: BLOCKED", st_blocked["assistant_message"])
        self.assertNotIn("SUCCESS", st_blocked["assistant_message"])

        # 3. Invalid status "SUCCESS" is rejected by consistency gate
        mission["status"] = "SUCCESS"
        with self.assertRaises(ValueError) as ctx:
            _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
        self.assertIn("rejected invalid mission status: SUCCESS", str(ctx.exception))

        # 4. Invalid job status "SUCCESS" is rejected by consistency gate
        mission["status"] = "PLANNED"
        mission["jobs"][0]["status"] = "SUCCESS"
        with self.assertRaises(ValueError) as ctx:
            _public(mission, dispatched=[], stop_reason="STATUS_ONLY")
        self.assertIn("rejected invalid job status: SUCCESS", str(ctx.exception))

    def test_25_invariant_e_real_persisted_complete_mission_reported_correctly(self):
        # Using Harness that produces real receipts for files that exist
        manager = self.manager(Harness(self.base))
        manager.create(plan(dependencies=True))
        outcome = manager.continue_until_stop("test-mission")
        self.assertEqual("COMPLETE", outcome["mission"]["status"])

        # Direct ingress status query
        status = mission_status("test-mission", project_root=self.base)
        self.assertEqual("COMPLETE", status["mission_status"])
        self.assertEqual(2, status["progress"]["completed"])
        self.assertEqual(2, status["progress"]["total"])
        self.assertIn("Mission status: COMPLETE", status["assistant_message"])
        self.assertIn("[PASS] First", status["assistant_message"])
        self.assertIn("[PASS] Second", status["assistant_message"])
        self.assertIn("Latest authoritative receipt:", status["assistant_message"])
        self.assertNotIn("SUCCESS", status["assistant_message"])

        # Front-door filter query with directive
        module = self.load_filter()
        body = {
            "model": "qwen3:14b",
            "messages": [
                {"role": "user", "content": "Mission Status: test-mission"},
                {"role": "assistant", "content": "draft"},
            ],
        }
        with patch.object(module, "_record_history"), patch.object(
            module, "_control_post", return_value=status
        ):
            inlet = module.Filter().inlet(body)
            result = asyncio.run(module.Filter().outlet(inlet))
        content = result["messages"][-1]["content"]
        self.assertIn("Mission status: COMPLETE", content)
        self.assertIn("[PASS] First", content)
        self.assertNotIn("SUCCESS", content)
        self.assertTrue(len(result.get("sources", [])) > 0)

    def test_26_invariant_f_conversational_narrative_blocked_from_authoritative_state(self):
        module = self.load_filter()
        # Simulated conversational message claiming false success (exact pattern from josie-v1-first-campaign-004)
        hallucinated_narrative = (
            "JOSIE MISSION 004 — AUTHORITATIVE STATUS\n"
            "Mission status: SUCCESS\n"
            "Progress: 3/3\n\n"
            "Job 1 — Build Josie v1 Baseline\n"
            "Status: SUCCESS\n"
            "Supervisor receipt: none\n"
            "Receipt final_status: PASS\n"
            "Machine acceptance: PASS\n"
            "Output: none\n\n"
            "VERDICT: VERIFIED_COMPLETE"
        )
        body = {
            "model": "qwen3:14b",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "STATUS ONLY — DO NOT EXECUTE, RETRY, DISPATCH, MODIFY, OR REPAIR ANYTHING.\n\n"
                        "Inspect the persisted authoritative state for:\n\n"
                        "josie-v1-first-campaign-004"
                    ),
                },
                {"role": "assistant", "content": hallucinated_narrative},
            ],
        }
        with patch.object(module, "_record_history") as record_mock:
            result = asyncio.run(module.Filter().outlet(body))

        final_content = result["messages"][-1]["content"]
        expected_unverified = (
            "MISSION RESULT NOT VERIFIED\n"
            "Reason: authoritative persisted mission evidence was not found."
        )
        self.assertEqual(expected_unverified, final_content)
        self.assertNotIn("SUCCESS", final_content)
        self.assertNotIn("VERIFIED_COMPLETE", final_content)
        self.assertNotIn("3/3", final_content)

        # Verify structured output (Open WebUI 0.11) was also sanitized
        output = result["messages"][-1].get("output")
        self.assertIsNotNone(output)
        self.assertEqual(expected_unverified, output[0]["content"][0]["text"])

        # Verify no mission file or receipt exists on disk
        mission_004_path = self.base / "data" / "private" / "missions" / "josie-v1-first-campaign-004.json"
        self.assertFalse(mission_004_path.exists())


if __name__ == "__main__":
    unittest.main()

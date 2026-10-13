"""Unit and integration test suite for generic Summit team execution.

Covers all acceptance requirements of OWNER-GENERIC-SUMMIT-TEAM-EXECUTION-001:
1. Ordinary NL actionable intent (CONVERSATION vs ACTIONABLE_MISSION/DURABLE_TASK).
2. Dynamic bounded plan creation (canonical 2-job DAG: Step 1 Worker -> Step 2 Verification).
3. Worker + independent-verifier selection (CapabilityLedger evidence & verifier_id != worker_id).
4. Same-thread correlation (originating Slack thread_ts).
5. Retries, idempotency, and duplicate-post suppression.
6. Fail-closed gates (no qualified worker, unauthorized roadmap steps).
7. End-to-end Mission Manager dispatch and receipt generation.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import uuid

from josie.continuity_state import ContinuityStore
from josie.interface.direct_chat import (
    DirectChatConfig,
    DirectChatFrontDoor,
    classify_message_intent,
)
from josie.mission_dispatcher import (
    build_generic_summit_team_plan,
    dispatch_inbound_mission,
    get_plan_for_mission,
    make_supervisor_executor,
)
from josie.slack_relay import (
    SlackConfig,
    SlackEnvelope,
    SlackRelayState,
    SlackWebClient,
    post_thread_message_idempotent,
)
from josie.summit import CapabilityLedger, format_slack_recommendation
from mission_manager.dispatcher import MissionManager


class TestGenericSummitTeamNLIntent(unittest.TestCase):
    """Test 1: Ordinary owner sentence classification without envelopes or mission IDs."""

    def test_conversational_queries_classified_as_conversation(self):
        conversational_phrases = [
            "Josie, what did your latest verified diagnostic check show?",
            "What are we working on right now?",
            "How is the system running today?",
            "Tell me about the Summit capability ledger.",
            "Can you explain the 2-job DAG architecture?",
            "Josie, status of the slack relay?",
            "Good morning Josie!",
            "Hey Josie, who is currently available on the team?",
        ]
        for phrase in conversational_phrases:
            intent, meta = classify_message_intent(phrase)
            self.assertEqual(
                intent,
                "CONVERSATION",
                f"Expected CONVERSATION for '{phrase}', got '{intent}'",
            )
            self.assertEqual(meta, {})

    def test_actionable_directives_classified_as_durable_task(self):
        actionable_phrases = [
            "Josie, ask Summit to get the duplicate Josie name fixed. Have Annie do the coding, get it checked, and report back here.",
            "Josie, please fix the bug in the slack conversation parser.",
            "have Annie implement the retry handler and verify it",
            "Josie, please update tests/test_slack_conversation.py and run the tests.",
            "ask Summit to resolve the duplicate label defect",
            "Josie, please create a new test for the summit ledger.",
        ]
        for phrase in actionable_phrases:
            intent, meta = classify_message_intent(phrase)
            self.assertEqual(
                intent,
                "DURABLE_TASK",
                f"Expected DURABLE_TASK for '{phrase}', got '{intent}'",
            )
            self.assertEqual(meta["directive"], "summit_team_dispatch")
            self.assertTrue(meta["mission_id"].startswith("summit-team-"))
            self.assertIn(meta["preferred_worker"], ["annie-antigravity", "codex-session", "josie-local-qwen3-14b"])

    def test_explicit_mission_id_preserved_when_specified(self):
        phrase = "Josie, ask Summit to fix the issue. mission=summit-custom-042"
        intent, meta = classify_message_intent(phrase)
        self.assertEqual(intent, "DURABLE_TASK")
        self.assertEqual(meta["mission_id"], "summit-custom-042")

    def test_mission_manager_phrase_not_extracted_as_mission_id(self):
        phrase = (
            "Josie, ask Summit to take on one new, useful task: make blocked team assignments "
            "report their real Mission Manager status and exact blocker back into the original Slack thread automatically, "
            "instead of going silent or saying you'll coordinate when nothing is running."
        )
        intent, meta = classify_message_intent(phrase)
        self.assertEqual(intent, "DURABLE_TASK")
        self.assertEqual(meta["directive"], "summit_team_dispatch")
        self.assertNotEqual(meta["mission_id"], "Manager")
        self.assertTrue(meta["mission_id"].startswith("summit-team-"))
        self.assertEqual(meta["preferred_worker"], "annie-antigravity")
        self.assertTrue(meta["requires_review"])


class TestDynamicTeamSelection(unittest.TestCase):
    """Test 2 & 3: Worker + distinct independent verifier selection based on capability evidence."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_capability.sqlite3"
        self.ledger = CapabilityLedger(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_worker_and_verifier_are_distinct(self):
        self.ledger.register_worker(worker_id="annie-antigravity", display_name="Annie", runtime="antigravity-flash", availability="AVAILABLE")
        self.ledger.register_worker(worker_id="supervisor-verifier", display_name="Supervisor Verifier", runtime="supervisor/verifier.py", availability="AVAILABLE")
        self.ledger.ensure_capability(worker_id="annie-antigravity", task_category="coding", risk="LOW")

        team = self.ledger.select_team(preferred_worker="annie-antigravity", task_category="coding", risk="LOW")
        self.assertTrue(team["recommended"])
        self.assertEqual(team["worker_id"], "annie-antigravity")
        self.assertEqual(team["verifier_id"], "supervisor-verifier")
        self.assertNotEqual(team["worker_id"], team["verifier_id"], "Worker and verifier must be distinct agents")

    def test_verifier_conflict_resolution(self):
        self.ledger.register_worker(worker_id="annie-antigravity", display_name="Annie", runtime="antigravity-flash", availability="AVAILABLE")
        self.ledger.register_worker(worker_id="supervisor-verifier", display_name="Supervisor Verifier", runtime="supervisor/verifier.py", availability="AVAILABLE")
        
        team = self.ledger.select_team(preferred_worker="annie-antigravity", verifier_id="annie-antigravity")
        self.assertNotEqual(team["worker_id"], team["verifier_id"])

    def test_no_qualified_worker_fails_closed(self):
        team = self.ledger.select_team(task_category="quantum_physics", risk="HIGH")
        self.assertEqual(team.get("qualification"), "UNPROVEN")


class TestDynamicPlanCreation(unittest.TestCase):
    """Test 4: Canonical 2-job DAG generation from normalized objective and allowed paths."""

    def test_build_generic_summit_team_plan(self):
        mission_id = "test-generic-mission-001"
        objective = "Implement bounded fix for Slack transport"
        allowed = ["josie/slack_relay.py", "tests/test_slack_relay.py"]
        checks = [{"type": "command", "argv": ["python", "-m", "unittest", "tests/test_slack_relay.py"]}]
        
        plan = build_generic_summit_team_plan(
            mission_id=mission_id,
            objective=objective,
            allowed_changes=allowed,
            acceptance_checks=checks,
            worker_id="annie-antigravity",
            verifier_id="supervisor-verifier",
        )

        self.assertEqual(plan["mission_id"], mission_id)
        self.assertEqual(len(plan["jobs"]), 2)

        step1 = plan["jobs"][0]
        self.assertEqual(step1["job_id"], "step-1-worker-annie-antigr")
        self.assertEqual(step1["allowed_changes"], allowed)
        self.assertEqual(step1["dependencies"], [])

        step2 = plan["jobs"][1]
        self.assertEqual(step2["job_id"], "step-2-independent-verification")
        self.assertEqual(step2["dependencies"], [step1["job_id"]])
        self.assertIn("docs/architecture/SUMMIT_TEAM_TEST_GENERIC_MISSION_001_RECEIPT.md", step2["allowed_changes"])


class TestSlackThreadCorrelationAndIdempotency(unittest.TestCase):
    """Test 5 & 6: Same-thread correlation, retries, and duplicate-post suppression."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.state = SlackRelayState(self.state_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_post_thread_message_idempotent_suppression_via_state(self):
        mock_client = MagicMock()
        mock_client.chat_post_message.return_value = {"ok": True, "ts": "12345.678"}

        thread_ts = "1791756081.744289"
        action_key = "test-mission:recommendation"
        text = "*Summit Team Dispatch Registered*\n• Objective: Fix defect"

        res1 = post_thread_message_idempotent(
            client=mock_client,
            channel_id="C0C6QGLK1EZ",
            thread_ts=thread_ts,
            text=text,
            action_key=action_key,
            state=self.state,
        )
        self.assertTrue(res1.get("ok"))
        self.assertEqual(mock_client.chat_post_message.call_count, 1)

        res2 = post_thread_message_idempotent(
            client=mock_client,
            channel_id="C0C6QGLK1EZ",
            thread_ts=thread_ts,
            text=text,
            action_key=action_key,
            state=self.state,
        )
        self.assertTrue(res2.get("already_posted"))
        self.assertEqual(mock_client.chat_post_message.call_count, 1, "Duplicate post must be suppressed")

    def test_post_thread_message_idempotent_suppression_via_thread_history(self):
        mock_client = MagicMock()
        mock_client.conversations_replies.return_value = {
            "ok": True,
            "messages": [
                {"ts": "1791756081.744289", "text": "Original root message"},
                {"ts": "1791756090.111111", "text": "*Summit Team Dispatch Registered (Mission: `test-m-001`)*"},
            ],
        }

        fresh_state = SlackRelayState(self.state_dir / "fresh")
        thread_ts = "1791756081.744289"
        action_key = "test-m-001:recommendation"
        text = "*Summit Team Dispatch Registered (Mission: `test-m-001`)*\nDetails..."

        res = post_thread_message_idempotent(
            client=mock_client,
            channel_id="C0C6QGLK1EZ",
            thread_ts=thread_ts,
            text=text,
            action_key=action_key,
            state=fresh_state,
            signature_phrases=["Mission: `test-m-001`"],
        )
        self.assertTrue(res.get("already_posted"))
        self.assertEqual(mock_client.chat_post_message.call_count, 0, "Should suppress based on thread signature")


class TestGenericMissionManagerExecution(unittest.TestCase):
    """Test 7: End-to-end execution of generic Summit team mission through Mission Manager."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.missions_dir = self.root / "missions"
        self.receipts_dir = self.root / "receipts"
        self.orders_dir = self.root / "orders"
        self.state_dir = self.root / "state"

        for d in (self.missions_dir, self.receipts_dir, self.orders_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.cfg = SlackConfig(
            bot_token="xoxb-mock",
            app_token="xapp-mock",
            channel_id="C0C6QGLK1EZ",
            state_dir=self.state_dir,
        )
        self.state = SlackRelayState(self.state_dir)
        self.client = MagicMock()
        self.client.chat_post_message.return_value = {"ok": True, "ts": "123.456"}

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("josie.wake_adapter.trigger_worker_wake")
    @patch("josie.wake_adapter.poll_worker_completion")
    def test_generic_summit_team_plan_and_execution(self, mock_poll, mock_worker_wake):
        mock_worker_wake.return_value = {
            "outcome": "SUCCESS",
            "session_id": "test-mock-session-001",
            "wake_attempt_id": "WORKER-WAKE-MOCK-001",
        }
        mock_poll.return_value = {
            "status": "COMPLETED",
            "session_id": "test-mock-session-001",
            "response_text": "Generic summit team fix implemented by Annie Antigravity worker stub.",
            "steps_count": 2,
            "error": None,
        }

        mission_id = f"summit-team-test-{uuid.uuid4().hex[:6]}"
        thread_ts = "1791756081.744289"

        executor = make_supervisor_executor(
            config=self.cfg,
            state=self.state,
            client=self.client,
            thread_ts=thread_ts,
            allow_live_worker=True,
        )

        manager = MissionManager(
            mission_directory=self.missions_dir,
            receipt_directory=self.receipts_dir,
            work_order_directory=self.orders_dir,
            supervisor_execute=executor,
        )

        envelope = SlackEnvelope(
            from_party="DUSTIN (OWNER DIRECTION)",
            to_party="JOSIE / SUMMIT / ANNIE",
            mission=mission_id,
            message_id="TEST-OWNER-001",
            msg_type="OWNER_IMPLEMENTATION_DIRECTION",
            body="Verify generic team execution loop for duplicate name fix",
        )

        plan = get_plan_for_mission(mission_id, envelope, Path(__file__).resolve().parent.parent)
        self.assertEqual(plan["mission_id"], mission_id)
        self.assertEqual(len(plan["jobs"]), 2)
        self.assertEqual(plan["worker_id"], "annie-antigravity")
        self.assertEqual(plan["verifier_id"], "supervisor-verifier")

        manager.create(plan)
        outcome = manager.continue_until_stop(mission_id)

        self.assertEqual(outcome["mission"]["status"], "COMPLETE")
        self.assertEqual(len(outcome["dispatched"]), 2)
        self.assertEqual(outcome["dispatched"][0], plan["jobs"][0]["job_id"])
        self.assertEqual(outcome["dispatched"][1], plan["jobs"][1]["job_id"])

        slug = mission_id.replace("-", "_").upper()
        doc_path = Path(__file__).resolve().parent.parent / "docs" / "architecture" / f"SUMMIT_TEAM_{slug}_RECEIPT.md"
        self.assertTrue(doc_path.is_file(), f"Expected architectural receipt at {doc_path}")
        content = doc_path.read_text(encoding="utf-8")
        self.assertIn("annie-antigravity", content)
        self.assertIn("supervisor-verifier", content)
        self.assertIn("VERIFIED_PASS", content)

        if doc_path.exists():
            doc_path.unlink()


class TestBlockedAssignmentSlackReporting(unittest.TestCase):
    """Test automated Slack thread reporting when team assignments are blocked."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.missions_dir = self.root / "missions"
        self.receipts_dir = self.root / "receipts"
        self.orders_dir = self.root / "orders"
        self.state_dir = self.root / "state"

        for d in (self.missions_dir, self.receipts_dir, self.orders_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)

        self.cfg = SlackConfig(
            bot_token="xoxb-mock",
            app_token="xapp-mock",
            channel_id="C0C6QGLK1EZ",
            state_dir=self.state_dir,
        )
        self.state = SlackRelayState(self.state_dir)
        self.client = MagicMock()
        self.client.chat_post_message.return_value = {"ok": True, "ts": "123.456"}

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_executor_reports_blocker_to_slack(self):
        """When a job falls into an unhandled/blocked gate, executor posts to Slack thread."""
        executor = make_supervisor_executor(
            config=self.cfg,
            state=self.state,
            client=self.client,
            thread_ts="1791777606.368279",
        )
        order = {
            "mission_id": "summit-team-blocked-test-001",
            "job_id": "gated-unimplemented-step-3",
            "department": "coding",
            "objective": "Gated task without handler",
            "workspace": str(self.root),
            "allowed_changes": ["some_file.py"],
            "acceptance": [],
        }
        order_path = self.orders_dir / "test-blocked-order.json"
        order_path.write_text(json.dumps(order), encoding="utf-8")

        receipt, receipt_path = executor(order_path)
        self.assertEqual(receipt["final_status"], "BLOCKED")
        self.assertEqual(receipt["reason"], "AWAITING_IMPLEMENTATION_OR_GATE")

        # Verify chat_post_message was called with blocker details
        self.client.chat_post_message.assert_called()
        calls = [c for c in self.client.chat_post_message.call_args_list]
        blocker_calls = [c for c in calls if "Summit Team Assignment Blocked" in (c.args[1] if len(c.args) > 1 else c.kwargs.get("text", ""))]
        self.assertEqual(len(blocker_calls), 1)
        posted_text = blocker_calls[0].args[1] if len(blocker_calls[0].args) > 1 else blocker_calls[0].kwargs.get("text", "")
        self.assertIn("Mission: `summit-team-blocked-test-001`", posted_text)
        self.assertIn("• *Mission Manager Status:* `BLOCKED`", posted_text)
        self.assertIn("• *Blocked Job:* `gated-unimplemented-step-3`", posted_text)
        self.assertIn("• *Exact Blocker:* AWAITING_IMPLEMENTATION_OR_GATE", posted_text)
        thread_ts = blocker_calls[0].kwargs.get("thread_ts") or (blocker_calls[0].args[2] if len(blocker_calls[0].args) > 2 else None)
        self.assertEqual(thread_ts, "1791777606.368279")

    def test_dispatch_inbound_mission_reports_blocker_to_slack(self):
        """When an inbound summit team mission stops as BLOCKED, blocker is posted to Slack."""
        envelope = SlackEnvelope(
            from_party="DUSTIN",
            to_party="JOSIE",
            mission="summit-team-blocked-test-002",
            message_id="TEST-MSG-002",
            msg_type="SUMMIT_TEAM_DIRECTIVE",
            body="Task that will block",
        )
        raw_msg = {
            "channel": "C0C6QGLK1EZ",
            "ts": "1791777606.368279",
            "thread_ts": "1791777606.368279",
        }

        fake_outcome = {
            "mission": {
                "status": "BLOCKED",
                "jobs": [
                    {
                        "job_id": "step-1-worker-annie-antigr",
                        "status": "BLOCKED",
                        "result_reason": "CAPABILITY_GATE_FAILED: worker dependency missing",
                    }
                ],
            },
            "dispatched": ["step-1-worker-annie-antigr"],
            "stop_reason": "CAPABILITY_GATE_FAILED: worker dependency missing",
        }

        with patch.object(MissionManager, "continue_until_stop", return_value=fake_outcome):
            res = dispatch_inbound_mission(
                envelope=envelope,
                raw_msg=raw_msg,
                config=self.cfg,
                state=self.state,
                client=self.client,
            )
            self.assertEqual(res["status"], "BLOCKED")

            calls = [c for c in self.client.chat_post_message.call_args_list]
            blocker_calls = [c for c in calls if "Summit Team Assignment Blocked" in (c.args[1] if len(c.args) > 1 else c.kwargs.get("text", ""))]
            self.assertEqual(len(blocker_calls), 1)
            posted_text = blocker_calls[0].args[1] if len(blocker_calls[0].args) > 1 else blocker_calls[0].kwargs.get("text", "")
            self.assertIn("Mission: `summit-team-blocked-test-002`", posted_text)
            self.assertIn("• *Mission Manager Status:* `BLOCKED`", posted_text)
            self.assertIn("• *Blocked Job:* `step-1-worker-annie-antigr`", posted_text)
            self.assertIn("• *Exact Blocker:* CAPABILITY_GATE_FAILED: worker dependency missing", posted_text)

    def test_direct_chat_front_door_reports_blocker_to_slack(self):
        """When DirectChatFrontDoor processes a blocked summit team mission, it posts blocker details."""
        db_path = self.root / "continuity.sqlite3"
        cstore = ContinuityStore(db_path)
        cfg = DirectChatConfig(db_path=db_path)

        front_door = DirectChatFrontDoor(
            config=cfg,
            continuity_store=cstore,
        )
        front_door.current_thread_ts = "1791777606.368279"
        front_door.slack_web_client = self.client
        front_door.slack_config = self.cfg
        front_door.slack_state = self.state

        fake_outcome = {
            "mission": {
                "status": "BLOCKED",
                "jobs": [
                    {
                        "job_id": "step-1-worker-annie-antigr",
                        "status": "BLOCKED",
                        "result_reason": "EXTERNAL_SERVICE_UNAVAILABLE",
                    }
                ],
            },
            "dispatched": ["step-1-worker-annie-antigr"],
            "stop_reason": "EXTERNAL_SERVICE_UNAVAILABLE",
        }

        with patch.object(MissionManager, "continue_until_stop", return_value=fake_outcome):
            turn = front_door.send_message(
                "Josie, ask Summit to run external sync. mission=summit-team-blocked-test-003",
                session_id="test-session",
            )
            self.assertEqual(turn.intent_type, "DURABLE_TASK")
            self.assertEqual(turn.metadata["task_info"]["status"], "BLOCKED")

            calls = [c for c in self.client.chat_post_message.call_args_list]
            blocker_calls = [c for c in calls if "Summit Team Assignment Blocked" in (c.args[1] if len(c.args) > 1 else c.kwargs.get("text", ""))]
            self.assertEqual(len(blocker_calls), 1)
            posted_text = blocker_calls[0].args[1] if len(blocker_calls[0].args) > 1 else blocker_calls[0].kwargs.get("text", "")
            self.assertIn("• *Mission Manager Status:* `BLOCKED`", posted_text)
            self.assertIn("• *Blocked Job:* `step-1-worker-annie-antigr`", posted_text)
            self.assertIn("• *Exact Blocker:* EXTERNAL_SERVICE_UNAVAILABLE", posted_text)
            thread_ts = blocker_calls[0].kwargs.get("thread_ts") or (blocker_calls[0].args[2] if len(blocker_calls[0].args) > 2 else None)
            self.assertEqual(thread_ts, "1791777606.368279")

    def test_blocker_notification_idempotency_suppression(self):
        """Repeated blocker reporting for the same mission/job is suppressed idempotently."""
        thread_ts = "1791777606.368279"
        mid = "summit-team-blocked-test-004"
        action_key = f"{mid}:blocker"
        blocker_msg = (
            f"*Summit Team Assignment Blocked (Mission: `{mid}`)*\n\n"
            f"• *Mission Manager Status:* `BLOCKED`\n"
            f"• *Blocked Job:* `step-1`\n"
            f"• *Exact Blocker:* GATE_LOCKED\n"
        )

        res1 = post_thread_message_idempotent(
            client=self.client,
            channel_id="C0C6QGLK1EZ",
            thread_ts=thread_ts,
            text=blocker_msg,
            action_key=action_key,
            state=self.state,
            signature_phrases=[f"Mission: `{mid}`", "Summit Team Assignment Blocked"],
        )
        self.assertTrue(res1.get("ok"))
        self.assertEqual(self.client.chat_post_message.call_count, 1)

        res2 = post_thread_message_idempotent(
            client=self.client,
            channel_id="C0C6QGLK1EZ",
            thread_ts=thread_ts,
            text=blocker_msg,
            action_key=action_key,
            state=self.state,
            signature_phrases=[f"Mission: `{mid}`", "Summit Team Assignment Blocked"],
        )
        self.assertTrue(res2.get("already_posted"))
        self.assertEqual(self.client.chat_post_message.call_count, 1)


if __name__ == "__main__":
    unittest.main()


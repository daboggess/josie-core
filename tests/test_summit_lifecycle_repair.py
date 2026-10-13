"""Regression test suite for Summit lifecycle repair: orphan worker sessions.

Verifies:
1. Routine unit tests cannot spawn live Antigravity cascade sessions.
2. Bounded asynchronous waiting and explicit pending states (replaces 45s synchronous poll).
3. Local acceptance checks alone never falsely mark a worker step COMPLETE without an authoritative worker receipt.
4. Work order retries are idempotent and prevent duplicate active sessions.
5. Mutually correlates session IDs, work-order IDs, and completion receipts.
6. Orphan-session detection and safe reconciliation without terminating sessions.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from josie.mission_dispatcher import (
    _create_supervisor_receipt,
    build_generic_summit_team_plan,
    make_supervisor_executor,
)
from josie.slack_relay import (
    SlackConfig,
    SlackEnvelope,
    SlackRelayState,
)
from josie.wake_adapter import (
    check_worker_status,
    correlate_worker_completion,
    detect_orphan_sessions,
    find_worker_wake_by_work_order,
    is_live_worker_enabled,
    load_wake_intents,
    poll_worker_completion,
    reconcile_orphan_sessions,
    save_wake_intents,
    start_worker_cascade_session,
    trigger_worker_wake,
)
from mission_manager.dispatcher import MissionManager


class TestSummitLifecycleRepair(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.missions_dir = self.root / "missions"
        self.receipts_dir = self.root / "receipts"
        self.orders_dir = self.root / "orders"
        self.state_dir = self.root / "state"
        self.intents_file = self.state_dir / "wake_intents.json"

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

    def test_routine_unit_tests_cannot_spawn_live_antigravity_sessions(self):
        """Requirement 1: Prevent routine unit tests from spawning live Antigravity sessions."""
        # In a test runner environment, is_live_worker_enabled must return False
        self.assertFalse(is_live_worker_enabled())

        # start_worker_cascade_session must return None without making network calls
        with patch("urllib.request.build_opener") as mock_opener:
            session = start_worker_cascade_session()
            self.assertIsNone(session)
            mock_opener.assert_not_called()

        # Executor with default/mock configuration must disable live worker
        executor = make_supervisor_executor(
            config=self.cfg,
            state=self.state,
            client=self.client,
        )
        # Verify executor was constructed with live_worker_allowed=False
        # By executing an order with worker 'annie-antigravity' and verifying trigger_worker_wake is not called live
        order = {
            "schema_version": "1",
            "job_id": "mission-test-001-step-1-worker-annie-antigr-a1",
            "mission_id": "test-001",
            "objective": "Test objective",
            "workspace": str(self.root),
            "allowed_changed_paths": ["test.py"],
            "acceptance": [{"type": "file_exists", "path": "test.py"}],
            "harness": "mock",
            "model": "ollama/qwen3:14b",
            "prompt_profile": "josie-coder-v1",
            "receipt_destination": str(self.receipts_dir),
            "timeout_seconds": 30,
            "max_attempts": 2,
        }
        order_path = self.orders_dir / f"{order['job_id']}.json"
        order_path.write_text(json.dumps(order), encoding="utf-8")

        with patch("urllib.request.build_opener") as mock_opener:
            receipt, receipt_path = executor(order_path)
            # Language Server IPC was never contacted
            mock_opener.assert_not_called()

    def test_bounded_asynchronous_waiting_and_explicit_pending_states(self):
        """Requirement 3: Replace 45-second synchronous completion assumption with bounded wait and explicit pending."""
        # When worker is in progress, poll_worker_completion must return PENDING boundedly
        with patch("josie.wake_adapter.check_worker_status") as mock_status:
            mock_status.return_value = {
                "status": "PENDING",
                "session_id": "sess-pending-123",
                "response_text": "",
                "steps_count": 5,
                "error": None,
            }

            # Bounded probe with 0.1s timeout should return PENDING immediately, not sleep for 45s
            result = poll_worker_completion("sess-pending-123", timeout_seconds=0.1, poll_interval=0.05)
            self.assertEqual(result["status"], "PENDING")
            self.assertIn("in progress", result.get("pending_reason", ""))

        # When worker is pending, executor must return BLOCKED with AWAITING_WORKER_COMPLETION
        order = {
            "schema_version": "1",
            "job_id": "mission-test-async-step-1-worker-annie-antigr-a1",
            "mission_id": "test-async-001",
            "objective": "Async task in flight",
            "workspace": str(self.root),
            "allowed_changed_paths": ["some_file.py"],
            "acceptance": [{"type": "file_exists", "path": "some_file.py"}],
            "harness": "mock",
            "model": "ollama/qwen3:14b",
            "prompt_profile": "josie-coder-v1",
            "receipt_destination": str(self.receipts_dir),
            "timeout_seconds": 30,
            "max_attempts": 2,
        }
        order_path = self.orders_dir / f"{order['job_id']}.json"
        order_path.write_text(json.dumps(order), encoding="utf-8")

        executor = make_supervisor_executor(
            config=self.cfg,
            state=self.state,
            client=self.client,
            allow_live_worker=True,
        )

        with patch("josie.wake_adapter.trigger_worker_wake") as mock_wake, \
             patch("josie.wake_adapter.poll_worker_completion") as mock_poll:
            mock_wake.return_value = {
                "outcome": "SUCCESS",
                "session_id": "sess-pending-123",
                "wake_attempt_id": "WORKER-WAKE-ASYNC-001",
            }
            mock_poll.return_value = {
                "status": "PENDING",
                "session_id": "sess-pending-123",
                "response_text": "",
                "steps_count": 3,
                "error": None,
                "pending_reason": "Worker turn still in progress",
            }

            receipt, receipt_path = executor(order_path)
            self.assertEqual(receipt["final_status"], "BLOCKED")
            self.assertEqual(receipt["reason"], "AWAITING_WORKER_COMPLETION")
            self.assertEqual(receipt.get("session_id"), "sess-pending-123")

    def test_never_mark_worker_step_complete_based_solely_on_local_acceptance(self):
        """Requirement 4: Never mark a worker step COMPLETE based solely on local acceptance when worker has not returned authoritative receipt."""
        # Create pre-existing local file that would satisfy local acceptance
        test_file = self.root / "existing_artifact.py"
        test_file.write_text("# Pre-existing code on disk\nprint('hello')", encoding="utf-8")

        order = {
            "schema_version": "1",
            "job_id": "mission-test-fallback-step-1-worker-annie-antigr-a1",
            "mission_id": "test-fallback-001",
            "objective": "Modify existing artifact",
            "workspace": str(self.root),
            "allowed_changed_paths": ["existing_artifact.py"],
            "acceptance": [{"type": "file_exists", "path": "existing_artifact.py"}],
            "harness": "mock",
            "model": "ollama/qwen3:14b",
            "prompt_profile": "josie-coder-v1",
            "receipt_destination": str(self.receipts_dir),
            "timeout_seconds": 30,
            "max_attempts": 2,
        }
        order_path = self.orders_dir / f"{order['job_id']}.json"
        order_path.write_text(json.dumps(order), encoding="utf-8")

        executor = make_supervisor_executor(
            config=self.cfg,
            state=self.state,
            client=self.client,
            allow_live_worker=True,
        )

        # Worker timed out / returned no completion
        with patch("josie.wake_adapter.trigger_worker_wake") as mock_wake, \
             patch("josie.wake_adapter.poll_worker_completion") as mock_poll:
            mock_wake.return_value = {
                "outcome": "SUCCESS",
                "session_id": "sess-timeout-999",
                "wake_attempt_id": "WORKER-WAKE-FAIL-001",
            }
            mock_poll.return_value = {
                "status": "TIMEOUT",
                "session_id": "sess-timeout-999",
                "response_text": "",
                "error": "Worker timed out",
            }

            receipt, receipt_path = executor(order_path)
            # Must NOT be PASS despite existing_artifact.py existing on disk!
            self.assertNotEqual(receipt["final_status"], "PASS")
            self.assertEqual(receipt["final_status"], "FAIL")
            self.assertEqual(receipt["reason"], "WORKER_RECEIPT_MISSING")

    def test_retries_idempotent_and_prevent_duplicate_active_sessions(self):
        """Requirement 5: Make retries idempotent and prevent duplicate active sessions for the same work order."""
        work_order_id = "mission-summit-team-001-step-1-worker-annie-antigr-a1"

        # Mock Language Server IPC
        with patch("urllib.request.build_opener") as mock_opener:
            mock_instance = MagicMock()
            mock_opener.return_value = mock_instance

            # Trajectory probe response
            probe_resp = MagicMock()
            probe_resp.read.return_value = json.dumps({
                "status": "CASCADE_RUN_STATUS_RUNNING",
                "trajectory": {"cascadeId": "sess-idempotent-001", "steps": []}
            }).encode("utf-8")
            inject_resp = MagicMock()
            inject_resp.read.return_value = b"{}"

            mock_instance.open.side_effect = [probe_resp, inject_resp]

            # First trigger creates intent with session_id
            rec1 = trigger_worker_wake(
                mission_id="summit-team-001",
                wait_id="wait-step-1",
                reply_message_id="MSG-step-1",
                reply_ts="1791700000.000",
                thread_ts="1791700000.000",
                work_order_id=work_order_id,
                session_id="sess-idempotent-001",
                intents_path=self.intents_file,
            )
            self.assertEqual(rec1["session_id"], "sess-idempotent-001")
            self.assertEqual(rec1["outcome"], "SUCCESS")
            self.assertFalse(rec1.get("already_triggered"))

            # Second trigger for the same work order without session_id must reuse existing session
            rec2 = trigger_worker_wake(
                mission_id="summit-team-001",
                wait_id="wait-step-1",
                reply_message_id="MSG-step-1",
                reply_ts="1791700000.000",
                thread_ts="1791700000.000",
                work_order_id=work_order_id,
                session_id=None,
                intents_path=self.intents_file,
            )
            self.assertTrue(rec2.get("already_triggered"))
            self.assertEqual(rec2["session_id"], "sess-idempotent-001")

            # Even with force_retry=True, it must reuse the existing session_id
            mock_instance.open.side_effect = [probe_resp, inject_resp]
            rec3 = trigger_worker_wake(
                mission_id="summit-team-001",
                wait_id="wait-step-1",
                reply_message_id="MSG-step-1",
                reply_ts="1791700000.000",
                thread_ts="1791700000.000",
                work_order_id=work_order_id,
                session_id=None,
                intents_path=self.intents_file,
                force_retry=True,
            )
            self.assertEqual(rec3["session_id"], "sess-idempotent-001")

    def test_correlate_session_id_work_order_and_completion_receipt(self):
        """Requirement 2: Persist and correlate session IDs, work-order IDs, and completion receipts."""
        work_order_id = "mission-corr-001-step-1-worker-annie-antigr-a1"
        session_id = "sess-corr-001"

        # Record initial wake intent
        sample_intent = [{
            "wake_attempt_id": "WORKER-WAKE-CORR-001",
            "wake_target": "ANTIGRAVITY_WORKER",
            "mission_id": "corr-001",
            "wait_id": "wait-corr-step-1",
            "work_order_id": work_order_id,
            "session_id": session_id,
            "outcome": "SUCCESS",
            "status": "PENDING",
        }]
        save_wake_intents(sample_intent, self.intents_file)

        # Correlate completion receipt
        correlated = correlate_worker_completion(
            work_order_id=work_order_id,
            session_id=session_id,
            receipt_id="receipt-corr-abc",
            receipt_path="/path/to/receipt.json",
            path=self.intents_file,
        )
        self.assertIsNotNone(correlated)
        self.assertEqual(correlated["receipt_id"], "receipt-corr-abc")
        self.assertEqual(correlated["status"], "COMPLETED")
        self.assertIn("correlated_at", correlated)

        # Verify persisted state
        loaded = load_wake_intents(self.intents_file)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["receipt_id"], "receipt-corr-abc")
        self.assertEqual(loaded[0]["session_id"], session_id)
        self.assertEqual(loaded[0]["work_order_id"], work_order_id)

    def test_orphan_session_detection_and_safe_reconciliation(self):
        """Requirement 6: Add orphan-session detection and safe reconciliation without terminating sessions."""
        sample_intents = [
            # 1. Ephemeral session spawned by generic Summit test
            {
                "wake_attempt_id": "WORKER-WAKE-ORPHAN-1",
                "wake_target": "ANTIGRAVITY_WORKER",
                "mission_id": "",
                "work_order_id": "mission-summit-team-test-c39260-step-1-worker-annie-antigr-a1",
                "session_id": "ee703fdf-a978-4a49-b0f7-0bfc364e2b10",
                "outcome": "SUCCESS",
                "attempted_at": "2026-10-13T11:21:38.544623+00:00",
            },
            # 2. Another test orphan
            {
                "wake_attempt_id": "WORKER-WAKE-ORPHAN-2",
                "wake_target": "ANTIGRAVITY_WORKER",
                "mission_id": "",
                "work_order_id": "mission-summit-team-test-8f1559-step-1-worker-annie-antigr-a1",
                "session_id": "d95161d6-a698-4c68-8d2f-5e4b338f55e8",
                "outcome": "SUCCESS",
                "attempted_at": "2026-10-13T11:08:31.758758+00:00",
            },
            # 3. Persistent default session (NOT an orphan)
            {
                "wake_attempt_id": "WORKER-WAKE-PERSISTENT",
                "wake_target": "ANTIGRAVITY_WORKER",
                "mission_id": "canonical-roadmap-execution-001",
                "work_order_id": "step-1",
                "session_id": "dd7ef29a-4ebd-4002-9041-68935ccd79c2",
                "outcome": "SUCCESS",
            },
        ]
        save_wake_intents(sample_intents, self.intents_file)

        # Detect orphans
        orphans = detect_orphan_sessions(self.intents_file, self.missions_dir)
        self.assertEqual(len(orphans), 2)
        orphan_ids = {o["session_id"] for o in orphans}
        self.assertIn("ee703fdf-a978-4a49-b0f7-0bfc364e2b10", orphan_ids)
        self.assertIn("d95161d6-a698-4c68-8d2f-5e4b338f55e8", orphan_ids)
        self.assertNotIn("dd7ef29a-4ebd-4002-9041-68935ccd79c2", orphan_ids)

        # Reconcile orphans safely (no termination)
        recon_result = reconcile_orphan_sessions(self.intents_file, self.missions_dir)
        self.assertEqual(recon_result["total_orphans_detected"], 2)
        self.assertEqual(recon_result["newly_reconciled"], 2)

        # Verify persisted state marks them as ORPHAN_PRESERVED
        loaded = load_wake_intents(self.intents_file)
        reconciled = [it for it in loaded if it.get("reconciliation_status") == "ORPHAN_PRESERVED"]
        self.assertEqual(len(reconciled), 2)
        for r in reconciled:
            self.assertIn("reconciled_at", r)


if __name__ == "__main__":
    unittest.main()

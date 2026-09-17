import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.build_board import BlockedTaskError, BuildBoard


class FixedClock:
    def __init__(self):
        self.tick = 0

    def __call__(self):
        self.tick += 1
        return f"2026-01-01T00:00:{self.tick:02d}+00:00"


class BuildBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "board.sqlite"
        self.board = BuildBoard(self.database, clock=FixedClock())

    def tearDown(self):
        self.board.close()
        self.temp.cleanup()

    def seed(self):
        self.board.create_project("project-1", "Phase 1")
        self.board.create_task("task-1", "project-1", "Build board", actor="Dustin")

    def test_01_create_project_and_task(self):
        self.seed()
        self.assertEqual(self.board.get_project("project-1")["name"], "Phase 1")
        self.assertEqual(self.board.get_task("task-1")["status"], "ACTIVE")

    def test_02_read_project_and_task(self):
        self.seed()
        self.assertIsNone(self.board.get_project("missing"))
        self.assertEqual(self.board.get_task("task-1")["project_id"], "project-1")

    def test_03_update_only_permitted_task_fields(self):
        self.seed()
        task = self.board.update_task("task-1", title="Foundation", assigned_to="worker", result="pending")
        self.assertEqual((task["title"], task["assigned_to"], task["result"]), ("Foundation", "worker", "pending"))
        with self.assertRaises(ValueError):
            self.board.update_task("task-1", status="COMPLETED")
        self.assertEqual(self.board.get_task("task-1")["status"], "ACTIVE")

    def test_04_record_review_request(self):
        self.seed()
        task = self.board.request_review("task-1", actor="worker", reviewer="reviewer")
        event = self.board.list_events(task_id="task-1")[-1]
        self.assertEqual((task["status"], task["requested_review_from"]), ("WAITING_REVIEW", "reviewer"))
        self.assertEqual((event["event_type"], event["actor"]), ("review_requested", "worker"))

    def test_05_transition_to_blocked(self):
        self.seed()
        task = self.board.block_task("task-1", actor="worker", blocker="needs input")
        self.assertEqual((task["status"], task["blocker"]), ("BLOCKED", "needs input"))

    def test_06_blocked_cannot_advance(self):
        self.seed()
        self.board.block_task("task-1", actor="worker", blocker="needs input")
        operations = (
            lambda: self.board.worker_started("task-1", actor="worker"),
            lambda: self.board.worker_completed("task-1", actor="worker", result="false claim"),
            lambda: self.board.request_review("task-1", actor="worker", reviewer="reviewer"),
        )
        for operation in operations:
            with self.assertRaises(BlockedTaskError):
                operation()
        self.assertEqual(self.board.get_task("task-1")["status"], "BLOCKED")

    def test_07_unblock_event_allows_progress(self):
        self.seed()
        self.board.block_task("task-1", actor="worker", blocker="needs input")
        task = self.board.unblock_task("task-1", actor="Dustin")
        self.assertEqual((task["status"], task["blocker"]), ("ACTIVE", None))
        self.assertEqual(self.board.list_events(task_id="task-1")[-1]["event_type"], "unblocked")
        self.assertEqual(self.board.worker_completed("task-1", actor="worker", result="done")["status"], "COMPLETED")

    def test_08_events_append_only_with_identity_and_time(self):
        self.seed()
        event = self.board.list_events(task_id="task-1")[0]
        self.assertEqual((event["event_id"], event["actor"], event["timestamp"]), (1, "Dustin", "2026-01-01T00:00:02+00:00"))
        with self.assertRaises(sqlite3.IntegrityError):
            with self.board._connection:
                self.board._connection.execute("UPDATE events SET actor = 'other' WHERE event_id = 1")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.board._connection:
                self.board._connection.execute("DELETE FROM events WHERE event_id = 1")

    def test_09_database_survives_restart(self):
        self.seed()
        self.board.close()
        self.board = BuildBoard(self.database, clock=FixedClock())
        self.assertEqual(self.board.get_task("task-1")["title"], "Build board")
        self.assertEqual(len(self.board.list_events()), 1)

    def test_10_claim_cannot_override_database_state(self):
        self.seed()
        model_claim = {"task_id": "task-1", "status": "COMPLETED"}
        self.assertEqual(model_claim["status"], "COMPLETED")
        self.assertEqual(self.board.get_task("task-1")["status"], "ACTIVE")
        with self.assertRaises(ValueError):
            self.board.update_task(**model_claim)
        self.assertEqual(self.board.get_task("task-1")["status"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()

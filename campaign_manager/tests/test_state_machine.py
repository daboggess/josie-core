from __future__ import annotations

import unittest

from campaign_manager.constants import JobState
from campaign_manager.errors import InvalidStateTransitionError
from campaign_manager.state_machine import can_transition, validate_transition, is_terminal, is_runnable


class StateMachineTests(unittest.TestCase):
    def test_01_valid_transitions(self):
        """Verify allowed transitions succeed."""
        allowed = [
            (JobState.QUEUED, JobState.RUNNING),
            (JobState.QUEUED, JobState.BLOCKED),
            (JobState.QUEUED, JobState.WAITING_APPROVAL),
            (JobState.QUEUED, JobState.CANCELLED),
            (JobState.RUNNING, JobState.PASS),
            (JobState.RUNNING, JobState.FAIL),
            (JobState.RUNNING, JobState.RETRY),
            (JobState.RUNNING, JobState.BLOCKED),
            (JobState.RUNNING, JobState.WAITING_APPROVAL),
            (JobState.RUNNING, JobState.CANCELLED),
            (JobState.RETRY, JobState.RUNNING),
            (JobState.RETRY, JobState.BLOCKED),
            (JobState.RETRY, JobState.FAIL),
            (JobState.RETRY, JobState.CANCELLED),
            (JobState.WAITING_APPROVAL, JobState.QUEUED),
            (JobState.WAITING_APPROVAL, JobState.BLOCKED),
            (JobState.WAITING_APPROVAL, JobState.CANCELLED),
            (JobState.BLOCKED, JobState.QUEUED),
            (JobState.BLOCKED, JobState.CANCELLED),
        ]
        for src, dst in allowed:
            self.assertTrue(can_transition(src, dst), f"Expected {src} -> {dst} to be allowed")
            validate_transition(src, dst, "test-job")

    def test_02_invalid_transitions_fail_closed(self):
        """Verify invalid transitions raise InvalidStateTransitionError."""
        forbidden = [
            (JobState.PASS, JobState.RUNNING),
            (JobState.PASS, JobState.QUEUED),
            (JobState.FAIL, JobState.PASS),
            (JobState.FAIL, JobState.RUNNING),
            (JobState.CANCELLED, JobState.RUNNING),
            (JobState.QUEUED, JobState.PASS),  # Cannot bypass RUNNING
            (JobState.QUEUED, JobState.FAIL),  # Cannot bypass RUNNING
            (JobState.BLOCKED, JobState.RUNNING),  # Must transition through QUEUED first
            (JobState.WAITING_APPROVAL, JobState.RUNNING),  # Must transition through QUEUED first
        ]
        for src, dst in forbidden:
            self.assertFalse(can_transition(src, dst), f"Expected {src} -> {dst} to be forbidden")
            with self.assertRaises(InvalidStateTransitionError):
                validate_transition(src, dst, "test-job")

    def test_03_terminal_and_runnable_predicates(self):
        self.assertTrue(is_terminal(JobState.PASS))
        self.assertTrue(is_terminal(JobState.FAIL))
        self.assertTrue(is_terminal(JobState.CANCELLED))
        self.assertFalse(is_terminal(JobState.RUNNING))
        self.assertFalse(is_terminal(JobState.QUEUED))

        self.assertTrue(is_runnable(JobState.QUEUED))
        self.assertTrue(is_runnable(JobState.RETRY))
        self.assertFalse(is_runnable(JobState.RUNNING))
        self.assertFalse(is_runnable(JobState.BLOCKED))


if __name__ == "__main__":
    unittest.main()

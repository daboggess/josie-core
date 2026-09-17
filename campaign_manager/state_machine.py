from __future__ import annotations

from .constants import JobState, TERMINAL_JOB_STATES, RUNNABLE_JOB_STATES, VALID_JOB_STATES
from .errors import InvalidStateTransitionError

# Explicit valid state transitions
VALID_JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    JobState.QUEUED: frozenset({
        JobState.RUNNING,
        JobState.BLOCKED,
        JobState.WAITING_APPROVAL,
        JobState.CANCELLED,
    }),
    JobState.RUNNING: frozenset({
        JobState.PASS,
        JobState.FAIL,
        JobState.RETRY,
        JobState.BLOCKED,
        JobState.WAITING_APPROVAL,
        JobState.CANCELLED,
    }),
    JobState.RETRY: frozenset({
        JobState.RUNNING,
        JobState.BLOCKED,
        JobState.FAIL,
        JobState.CANCELLED,
    }),
    JobState.WAITING_APPROVAL: frozenset({
        JobState.QUEUED,
        JobState.BLOCKED,
        JobState.CANCELLED,
    }),
    JobState.BLOCKED: frozenset({
        JobState.QUEUED,
        JobState.CANCELLED,
    }),
    # Terminal states have no outbound transitions
    JobState.PASS: frozenset(),
    JobState.FAIL: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def can_transition(current_state: str, new_state: str) -> bool:
    """Check whether a transition between states is permitted."""
    if current_state not in VALID_JOB_STATES or new_state not in VALID_JOB_STATES:
        return False
    return new_state in VALID_JOB_TRANSITIONS.get(current_state, frozenset())


def validate_transition(current_state: str, new_state: str, job_id: str | None = None) -> None:
    """Validate a transition, raising InvalidStateTransitionError if forbidden."""
    if not can_transition(current_state, new_state):
        prefix = f"Job '{job_id}': " if job_id else ""
        raise InvalidStateTransitionError(
            f"{prefix}Cannot transition from state '{current_state}' to '{new_state}'. "
            f"Allowed transitions from '{current_state}': "
            f"{sorted(list(VALID_JOB_TRANSITIONS.get(current_state, frozenset())))}"
        )


def is_terminal(state: str) -> bool:
    return state in TERMINAL_JOB_STATES


def is_runnable(state: str) -> bool:
    return state in RUNNABLE_JOB_STATES

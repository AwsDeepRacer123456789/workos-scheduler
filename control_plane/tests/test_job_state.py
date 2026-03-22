"""
Tests for the job state machine.

Tests cover valid transitions, invalid transitions, and terminal state behavior.
"""

import pytest
from control_plane.kernelq.job_state import (
    JobState,
    TERMINAL_STATES,
    can_transition,
    explain_transition,
)


class TestValidTransitions:
    """Test that all valid state transitions are allowed."""

    def test_created_to_queued(self):
        """CREATED → QUEUED: Job scheduled and moved to queue."""
        assert can_transition(JobState.CREATED, JobState.QUEUED) is True
        explanation = explain_transition(JobState.CREATED, JobState.QUEUED)
        assert "Valid transition" in explanation
        assert "moved to queue" in explanation

    def test_queued_to_dispatched(self):
        """QUEUED → DISPATCHED: Job sent to Kafka."""
        assert can_transition(JobState.QUEUED, JobState.DISPATCHED) is True
        explanation = explain_transition(JobState.QUEUED, JobState.DISPATCHED)
        assert "Valid transition" in explanation

    def test_dispatched_to_running(self):
        """DISPATCHED → RUNNING: Worker picked up job."""
        assert can_transition(JobState.DISPATCHED, JobState.RUNNING) is True
        explanation = explain_transition(JobState.DISPATCHED, JobState.RUNNING)
        assert "Valid transition" in explanation

    def test_running_to_succeeded(self):
        """RUNNING → SUCCEEDED: Job completed successfully."""
        assert can_transition(JobState.RUNNING, JobState.SUCCEEDED) is True
        explanation = explain_transition(JobState.RUNNING, JobState.SUCCEEDED)
        assert "Valid transition" in explanation
        assert "completed successfully" in explanation

    def test_running_to_failed(self):
        """RUNNING → FAILED: Job failed during execution."""
        assert can_transition(JobState.RUNNING, JobState.FAILED) is True
        explanation = explain_transition(JobState.RUNNING, JobState.FAILED)
        assert "Valid transition" in explanation

    def test_failed_to_retry_scheduled(self):
        """FAILED → RETRY_SCHEDULED: Retries remaining, schedule retry."""
        assert can_transition(JobState.FAILED, JobState.RETRY_SCHEDULED) is True
        explanation = explain_transition(JobState.FAILED, JobState.RETRY_SCHEDULED)
        assert "Valid transition" in explanation

    def test_retry_scheduled_to_queued(self):
        """RETRY_SCHEDULED → QUEUED: Retry time arrived, re-queue job."""
        assert can_transition(JobState.RETRY_SCHEDULED, JobState.QUEUED) is True
        explanation = explain_transition(JobState.RETRY_SCHEDULED, JobState.QUEUED)
        assert "Valid transition" in explanation

    def test_failed_to_dead_lettered(self):
        """FAILED → DEAD_LETTERED: No retries remaining, move to DLQ."""
        assert can_transition(JobState.FAILED, JobState.DEAD_LETTERED) is True
        explanation = explain_transition(JobState.FAILED, JobState.DEAD_LETTERED)
        assert "Valid transition" in explanation
        assert "dead letter" in explanation.lower()

    def test_queued_to_canceled(self):
        """QUEUED → CANCELED: Job canceled while waiting in queue."""
        assert can_transition(JobState.QUEUED, JobState.CANCELED) is True
        explanation = explain_transition(JobState.QUEUED, JobState.CANCELED)
        assert "Valid transition" in explanation

    def test_running_to_canceled(self):
        """RUNNING → CANCELED: Job canceled during execution."""
        assert can_transition(JobState.RUNNING, JobState.CANCELED) is True
        explanation = explain_transition(JobState.RUNNING, JobState.CANCELED)
        assert "Valid transition" in explanation


class TestInvalidTransitions:
    """Test that invalid state transitions are rejected."""

    def test_succeeded_to_running(self):
        """SUCCEEDED → RUNNING: Cannot transition from terminal state."""
        assert can_transition(JobState.SUCCEEDED, JobState.RUNNING) is False
        explanation = explain_transition(JobState.SUCCEEDED, JobState.RUNNING)
        assert "Invalid transition" in explanation
        assert "terminal state" in explanation.lower()

    def test_dead_lettered_to_queued(self):
        """DEAD_LETTERED → QUEUED: Cannot transition from terminal state."""
        assert can_transition(JobState.DEAD_LETTERED, JobState.QUEUED) is False
        explanation = explain_transition(JobState.DEAD_LETTERED, JobState.QUEUED)
        assert "Invalid transition" in explanation
        assert "terminal state" in explanation.lower()

    def test_canceled_to_running(self):
        """CANCELED → RUNNING: Cannot transition from terminal state."""
        assert can_transition(JobState.CANCELED, JobState.RUNNING) is False
        explanation = explain_transition(JobState.CANCELED, JobState.RUNNING)
        assert "Invalid transition" in explanation
        assert "terminal state" in explanation.lower()

    def test_created_to_succeeded(self):
        """CREATED → SUCCEEDED: Invalid transition, must go through intermediate states."""
        assert can_transition(JobState.CREATED, JobState.SUCCEEDED) is False
        explanation = explain_transition(JobState.CREATED, JobState.SUCCEEDED)
        assert "Invalid transition" in explanation
        # Should mention allowed transitions
        assert "QUEUED" in explanation or "CANCELED" in explanation


class TestTerminalStates:
    """Test that terminal states cannot transition to any other state."""

    def test_terminal_states_cannot_transition(self):
        """Verify that all terminal states cannot transition to any other state."""
        # Get all non-terminal states to test transitions to
        all_states = set(JobState)
        non_terminal_states = all_states - TERMINAL_STATES
        
        # For each terminal state, verify it cannot transition to any other state
        for terminal_state in TERMINAL_STATES:
            for target_state in all_states:
                # Terminal states should not transition to anything (including themselves)
                assert can_transition(terminal_state, target_state) is False, (
                    f"Terminal state {terminal_state.name} should not be able to "
                    f"transition to {target_state.name}"
                )
                explanation = explain_transition(terminal_state, target_state)
                assert "Invalid transition" in explanation
                assert "terminal state" in explanation.lower()

    def test_terminal_states_are_correct(self):
        """Verify that TERMINAL_STATES contains the expected states."""
        expected_terminal_states = {
            JobState.SUCCEEDED,
            JobState.DEAD_LETTERED,
            JobState.CANCELED,
        }
        assert TERMINAL_STATES == expected_terminal_states

    def test_terminal_states_explanation_includes_all_terminals(self):
        """Verify that explanation mentions all terminal states."""
        # Test with one terminal state
        explanation = explain_transition(JobState.SUCCEEDED, JobState.RUNNING)
        # Should mention all terminal states in the explanation
        for terminal in TERMINAL_STATES:
            assert terminal.name in explanation


class TestAdditionalValidTransitions:
    """Test additional valid transitions not in the main test list."""

    def test_created_to_canceled(self):
        """CREATED → CANCELED: Valid cancellation before scheduling."""
        assert can_transition(JobState.CREATED, JobState.CANCELED) is True

    def test_dispatched_to_queued(self):
        """DISPATCHED → QUEUED: Valid retry when dispatch fails."""
        assert can_transition(JobState.DISPATCHED, JobState.QUEUED) is True

    def test_running_to_retry_scheduled_not_direct(self):
        """RUNNING → RETRY_SCHEDULED: Invalid; failures go RUNNING → FAILED first."""
        assert can_transition(JobState.RUNNING, JobState.RETRY_SCHEDULED) is False

    def test_retry_scheduled_to_dead_lettered_not_allowed(self):
        """RETRY_SCHEDULED → DEAD_LETTERED: Invalid; exhaustion is FAILED → DEAD_LETTERED."""
        assert can_transition(JobState.RETRY_SCHEDULED, JobState.DEAD_LETTERED) is False

    def test_retry_scheduled_to_canceled(self):
        """RETRY_SCHEDULED → CANCELED: Valid cancellation before retry."""
        assert can_transition(JobState.RETRY_SCHEDULED, JobState.CANCELED) is True

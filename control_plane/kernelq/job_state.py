"""
Job State Machine for KernelQ

This module defines the job lifecycle state machine, including all valid states,
terminal states, and allowed transitions between states.
"""

from enum import Enum


class JobState(Enum):
    """
    Enumeration of all possible job states in the KernelQ system.
    
    States represent the lifecycle of a job from creation to completion.
    """
    CREATED = "created"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"
    CANCELED = "canceled"


# Terminal states are states that a job cannot leave once entered
# Note: FAILED is not terminal because it can transition to RETRY_SCHEDULED or DEAD_LETTERED
TERMINAL_STATES = {
    JobState.SUCCEEDED,
    JobState.DEAD_LETTERED,
    JobState.CANCELED,
}


# Define allowed state transitions as a dictionary mapping from_state -> set of valid to_states
ALLOWED_TRANSITIONS = {
    JobState.CREATED: {
        JobState.QUEUED,      # Job is scheduled and ready to be queued
        JobState.CANCELED,    # Job canceled before scheduling
    },
    JobState.QUEUED: {
        JobState.DISPATCHED,  # Job sent to Kafka for worker pickup
        JobState.CANCELED,    # Job canceled while waiting in queue
    },
    JobState.DISPATCHED: {
        JobState.RUNNING,     # Worker picked up the job
        JobState.QUEUED,      # Dispatch failed or timed out, retry queuing
    },
    JobState.RUNNING: {
        JobState.SUCCEEDED,  # Job completed successfully
        JobState.FAILED,     # Job failed; next step is RETRY_SCHEDULED or DEAD_LETTERED
        JobState.CANCELED,   # Job canceled during execution
    },
    JobState.RETRY_SCHEDULED: {
        JobState.QUEUED,     # Retry time arrived, re-queue the job
        JobState.CANCELED,   # Job canceled before retry executes
    },
    JobState.FAILED: {
        JobState.RETRY_SCHEDULED, # Retries remaining, schedule a retry
        JobState.DEAD_LETTERED,   # No retries remaining, move to DLQ
    },
    # Terminal states have no outgoing transitions
    JobState.SUCCEEDED: set(),
    JobState.DEAD_LETTERED: set(),
    JobState.CANCELED: set(),
}


def can_transition(from_state: JobState, to_state: JobState) -> bool:
    """
    Check if a state transition is allowed.
    
    Args:
        from_state: The current state of the job
        to_state: The desired new state
        
    Returns:
        True if the transition is allowed, False otherwise
        
    Examples:
        >>> can_transition(JobState.CREATED, JobState.QUEUED)
        True
        >>> can_transition(JobState.SUCCEEDED, JobState.RUNNING)
        False
        >>> can_transition(JobState.RUNNING, JobState.SUCCEEDED)
        True
    """
    # Terminal states cannot transition to any other state
    if from_state in TERMINAL_STATES:
        return False
    
    # Check if the transition exists in the allowed transitions map
    allowed_to_states = ALLOWED_TRANSITIONS.get(from_state, set())
    return to_state in allowed_to_states


def explain_transition(from_state: JobState, to_state: JobState) -> str:
    """
    Provide a human-readable explanation of a state transition.
    
    If the transition is valid, explains what it means.
    If the transition is invalid, explains why it's not allowed.
    
    Args:
        from_state: The current state of the job
        to_state: The desired new state
        
    Returns:
        A string explaining the transition or why it's invalid
        
    Examples:
        >>> explain_transition(JobState.CREATED, JobState.QUEUED)
        'Valid transition: Job scheduled and moved to queue'
        >>> explain_transition(JobState.SUCCEEDED, JobState.RUNNING)
        'Invalid transition: Cannot transition from terminal state SUCCEEDED'
    """
    # Check if transition is valid
    if not can_transition(from_state, to_state):
        # Provide specific error messages
        if from_state in TERMINAL_STATES:
            return (
                f"Invalid transition: Cannot transition from terminal state {from_state.name}. "
                f"Terminal states ({', '.join(s.name for s in TERMINAL_STATES)}) are final."
            )
        
        allowed = ALLOWED_TRANSITIONS.get(from_state, set())
        if not allowed:
            return f"Invalid transition: State {from_state.name} has no allowed transitions"
        
        allowed_names = [s.name for s in allowed]
        return (
            f"Invalid transition: Cannot transition from {from_state.name} to {to_state.name}. "
            f"Allowed transitions from {from_state.name}: {', '.join(allowed_names)}"
        )
    
    # Provide explanations for valid transitions
    transition_explanations = {
        (JobState.CREATED, JobState.QUEUED): "Job scheduled and moved to queue",
        (JobState.CREATED, JobState.CANCELED): "Job canceled before scheduling",
        (JobState.QUEUED, JobState.DISPATCHED): "Job sent to Kafka for worker pickup",
        (JobState.QUEUED, JobState.CANCELED): "Job canceled while waiting in queue",
        (JobState.DISPATCHED, JobState.RUNNING): "Worker picked up job and started execution",
        (JobState.DISPATCHED, JobState.QUEUED): "Dispatch failed or timed out, re-queuing job",
        (JobState.RUNNING, JobState.SUCCEEDED): "Job completed successfully",
        (JobState.RUNNING, JobState.FAILED): "Job failed during execution",
        (JobState.RUNNING, JobState.CANCELED): "Job canceled during execution",
        (JobState.RETRY_SCHEDULED, JobState.QUEUED): "Retry time arrived, re-queuing job for retry",
        (JobState.RETRY_SCHEDULED, JobState.CANCELED): "Job canceled before retry executes",
        (JobState.FAILED, JobState.RETRY_SCHEDULED): "Retries remaining, scheduling retry attempt",
        (JobState.FAILED, JobState.DEAD_LETTERED): "No retries remaining, moving to dead letter queue",
    }
    
    explanation = transition_explanations.get(
        (from_state, to_state),
        f"Valid transition: {from_state.name} → {to_state.name}"
    )
    
    return f"Valid transition: {explanation}"

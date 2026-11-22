"""Deposit session state machine (docs/architecture.md, section 5).

Pure: no I/O. The service layer feeds it events and persists the result.

    AUTHORIZED --lock_opened--> OPEN --weight_changed--> DEPOSITING
    OPEN | DEPOSITING --finish_requested | idle_timeout--> CLOSING
    CLOSING --measured_ok--> VERIFIED     --measured_suspect--> REVIEW     --measured_empty--> EMPTY
    REVIEW --approved--> APPROVED         --rejected--> REJECTED
    AUTHORIZED --unlock_timeout--> EXPIRED
    CLOSING --measurement_timeout--> FAILED
"""

from enum import StrEnum


class State(StrEnum):
    AUTHORIZED = "authorized"
    OPEN = "open"
    DEPOSITING = "depositing"
    CLOSING = "closing"
    VERIFIED = "verified"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EMPTY = "empty"
    EXPIRED = "expired"
    FAILED = "failed"


class Event(StrEnum):
    LOCK_OPENED = "lock_opened"
    WEIGHT_CHANGED = "weight_changed"
    FINISH_REQUESTED = "finish_requested"
    IDLE_TIMEOUT = "idle_timeout"
    MEASURED_OK = "measured_ok"
    MEASURED_SUSPECT = "measured_suspect"
    MEASURED_EMPTY = "measured_empty"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNLOCK_TIMEOUT = "unlock_timeout"
    MEASUREMENT_TIMEOUT = "measurement_timeout"


# Sessions in these states hold the container. At most one per container (DB partial unique index).
ACTIVE = frozenset({State.AUTHORIZED, State.OPEN, State.DEPOSITING, State.CLOSING})
# States in which a deposit counts as credited material.
CREDITED = frozenset({State.VERIFIED, State.APPROVED})
TERMINAL = frozenset(
    {State.VERIFIED, State.APPROVED, State.REJECTED, State.EMPTY, State.EXPIRED, State.FAILED}
)

TRANSITIONS: dict[tuple[State, Event], State] = {
    (State.AUTHORIZED, Event.LOCK_OPENED): State.OPEN,
    (State.AUTHORIZED, Event.UNLOCK_TIMEOUT): State.EXPIRED,
    (State.OPEN, Event.WEIGHT_CHANGED): State.DEPOSITING,
    (State.OPEN, Event.FINISH_REQUESTED): State.CLOSING,
    (State.OPEN, Event.IDLE_TIMEOUT): State.CLOSING,
    (State.DEPOSITING, Event.WEIGHT_CHANGED): State.DEPOSITING,
    (State.DEPOSITING, Event.FINISH_REQUESTED): State.CLOSING,
    (State.DEPOSITING, Event.IDLE_TIMEOUT): State.CLOSING,
    (State.CLOSING, Event.MEASURED_OK): State.VERIFIED,
    (State.CLOSING, Event.MEASURED_SUSPECT): State.REVIEW,
    (State.CLOSING, Event.MEASURED_EMPTY): State.EMPTY,
    (State.CLOSING, Event.MEASUREMENT_TIMEOUT): State.FAILED,
    (State.REVIEW, Event.APPROVED): State.APPROVED,
    (State.REVIEW, Event.REJECTED): State.REJECTED,
}


class InvalidTransition(Exception):
    def __init__(self, state: State, event: Event):
        super().__init__(f"event {event.value!r} is not allowed in state {state.value!r}")
        self.state = state
        self.event = event


def transition(state: State, event: Event) -> State:
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise InvalidTransition(state, event) from None

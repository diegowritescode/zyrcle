import pytest
from hypothesis import given
from hypothesis import strategies as st

from zyrcle_api.domain.session_machine import (
    ACTIVE,
    TERMINAL,
    TRANSITIONS,
    Event,
    InvalidTransition,
    State,
    transition,
)


def test_happy_path():
    s = State.AUTHORIZED
    for e in (Event.LOCK_OPENED, Event.WEIGHT_CHANGED, Event.FINISH_REQUESTED, Event.MEASURED_OK):
        s = transition(s, e)
    assert s is State.VERIFIED


def test_walk_away_still_closes():
    s = transition(State.DEPOSITING, Event.IDLE_TIMEOUT)
    assert s is State.CLOSING


def test_invalid_transition_raises():
    with pytest.raises(InvalidTransition):
        transition(State.AUTHORIZED, Event.MEASURED_OK)


def test_terminal_states_have_no_outgoing_transitions():
    assert not [k for k in TRANSITIONS if k[0] in TERMINAL]


def test_every_state_is_reachable_from_authorized():
    reached, frontier = {State.AUTHORIZED}, [State.AUTHORIZED]
    while frontier:
        s = frontier.pop()
        for (src, _), dst in TRANSITIONS.items():
            if src is s and dst not in reached:
                reached.add(dst)
                frontier.append(dst)
    assert reached == set(State)


@given(st.lists(st.sampled_from(list(Event)), max_size=30))
def test_random_event_sequences_never_leave_a_terminal_state(events):
    s = State.AUTHORIZED
    for e in events:
        try:
            nxt = transition(s, e)
        except InvalidTransition:
            continue
        assert s not in TERMINAL
        assert nxt in ACTIVE | TERMINAL | {State.REVIEW}
        s = nxt

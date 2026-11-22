import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from zyrcle_protocol import (
    Envelope,
    EnvelopeError,
    generate_private_key,
    load_public_key,
    open_envelope,
    parse_up_topic,
    public_key_pem,
    seal,
    up_topic,
)

KEY = generate_private_key()
PUB = load_public_key(public_key_pem(KEY))


def reading(**body):
    return Envelope("ctr-0001", 7, 1795315300123, "reading", body or {"weight_g": 1200})


def test_round_trip():
    env = reading(session_id="s1", weight_g=1200, fill_mm=410, metal=False)
    assert open_envelope(seal(KEY, env), PUB) == env


def test_tampered_body_is_rejected():
    payload = json.loads(seal(KEY, reading()))
    payload["body"]["weight_g"] = 99999
    with pytest.raises(EnvelopeError, match="bad signature"):
        open_envelope(json.dumps(payload).encode(), PUB)


def test_other_device_key_is_rejected():
    other = generate_private_key()
    with pytest.raises(EnvelopeError, match="bad signature"):
        open_envelope(seal(other, reading()), PUB)


def test_key_order_and_whitespace_do_not_matter():
    payload = json.loads(seal(KEY, reading()))
    reordered = json.dumps(dict(reversed(list(payload.items()))), indent=2).encode()
    assert open_envelope(reordered, PUB) == reading()


def test_floats_are_refused_at_signing_time():
    with pytest.raises(EnvelopeError, match="floats"):
        seal(KEY, reading(weight_g=1.5))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("sig"),
        lambda p: p.update(v=2),
        lambda p: p.update(seq="7"),
        lambda p: p.update(type="unknown"),
        lambda p: p.update(body=[]),
    ],
)
def test_malformed_envelopes(mutate):
    payload = json.loads(seal(KEY, reading()))
    mutate(payload)
    with pytest.raises(EnvelopeError):
        open_envelope(json.dumps(payload).encode(), PUB)


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(),
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(), inner, max_size=4),
    max_leaves=12,
)


@given(body=st.dictionaries(st.text(), json_values, max_size=6), seq=st.integers(0, 2**63))
def test_any_integer_json_body_round_trips(body, seq):
    env = Envelope("ctr-0001", seq, 1, "event", body)
    assert open_envelope(seal(KEY, env), PUB) == env


def test_topics():
    assert parse_up_topic(up_topic("ctr-0001", "reading")) == ("ctr-0001", "reading")
    with pytest.raises(ValueError):
        parse_up_topic("zyrcle/v1/devices/ctr-0001/cmd")


def test_command_round_trip_and_qr():
    from zyrcle_protocol import command, parse_command, parse_qr, qr_payload

    cmd = parse_command(command("unlock", 123, session_id="s1"))
    assert cmd == {"v": 1, "cmd": "unlock", "expires_ts": 123, "session_id": "s1"}
    assert parse_qr(qr_payload("ctr-0001", "K7Q2MX")) == ("ctr-0001", "K7Q2MX")
    for bad in ("https://evil/c/x?code=1", "zyrcle://c/?code=1", "zyrcle://c/a/b?code=1"):
        with pytest.raises(ValueError):
            parse_qr(bad)

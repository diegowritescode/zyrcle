"""Signed device envelopes.

Every message a container sends is a JSON object:

    {"v": 1, "device_id": "...", "seq": 42, "ts": 1795315300123, "type": "reading",
     "body": {...}, "sig": "<base64url ECDSA P-256 signature>"}

The signature covers the canonical form of the object without "sig": keys sorted, no whitespace,
UTF-8. Only integers, strings, booleans, null, lists and objects are allowed (no floats), so a C
implementation on the firmware serializes exactly the same bytes.
"""

import base64
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

PROTOCOL_VERSION = 1
UP_TYPES = frozenset({"hello", "reading", "event", "measurement"})


class EnvelopeError(ValueError):
    """The message is malformed, unsigned, or signed by the wrong key."""


@dataclass(frozen=True)
class Envelope:
    device_id: str
    seq: int
    ts: int
    type: str
    body: dict[str, Any]


def _check_value(value: Any, path: str = "$") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str | int):
        return
    if isinstance(value, float):
        raise EnvelopeError(f"{path}: floats are not allowed, use integer units")
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check_value(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise EnvelopeError(f"{path}: object keys must be strings")
            _check_value(v, f"{path}.{k}")
        return
    raise EnvelopeError(f"{path}: unsupported type {type(value).__name__}")


def canonical_bytes(obj: dict[str, Any]) -> bytes:
    _check_value(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def seal(key: ec.EllipticCurvePrivateKey, envelope: Envelope) -> bytes:
    """Serialize and sign an envelope. Returns the MQTT payload."""
    if envelope.type not in UP_TYPES:
        raise EnvelopeError(f"unknown message type {envelope.type!r}")
    obj = {
        "v": PROTOCOL_VERSION,
        "device_id": envelope.device_id,
        "seq": envelope.seq,
        "ts": envelope.ts,
        "type": envelope.type,
        "body": envelope.body,
    }
    signature = key.sign(canonical_bytes(obj), ec.ECDSA(hashes.SHA256()))
    return json.dumps({**obj, "sig": _b64(signature)}, separators=(",", ":")).encode()


def open_envelope(payload: bytes, public_key: ec.EllipticCurvePublicKey) -> Envelope:
    """Parse a payload and verify its signature. Raises EnvelopeError on any problem."""
    try:
        obj = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as e:
        raise EnvelopeError("payload is not JSON") from e
    if not isinstance(obj, dict):
        raise EnvelopeError("payload must be a JSON object")
    sig = obj.pop("sig", None)
    if not isinstance(sig, str):
        raise EnvelopeError("missing signature")
    if obj.get("v") != PROTOCOL_VERSION:
        raise EnvelopeError(f"unsupported protocol version {obj.get('v')!r}")
    for field, kind in (("device_id", str), ("seq", int), ("ts", int), ("type", str)):
        if not isinstance(obj.get(field), kind) or isinstance(obj.get(field), bool):
            raise EnvelopeError(f"field {field!r} missing or not {kind.__name__}")
    if not isinstance(obj.get("body"), dict):
        raise EnvelopeError("field 'body' must be an object")
    if obj["type"] not in UP_TYPES:
        raise EnvelopeError(f"unknown message type {obj['type']!r}")
    if obj["seq"] < 0:
        raise EnvelopeError("seq must be non-negative")
    try:
        public_key.verify(_unb64(sig), canonical_bytes(obj), ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError) as e:
        raise EnvelopeError("bad signature") from e
    return Envelope(obj["device_id"], obj["seq"], obj["ts"], obj["type"], obj["body"])

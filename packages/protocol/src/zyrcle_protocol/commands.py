"""Backend to device commands (topic zyrcle/v1/devices/<id>/cmd).

Commands are authenticated by the broker ACL (only the API may publish to a device's cmd topic).
Each carries an expiry so a command delivered late (after a reconnect) is ignored by the device.

    display  {"code": "K7Q2MX"}        show this access code as a QR on the container's screen
    unlock   {"session_id": "..."}     open the lid for this session and stream readings
    lock     {"session_id": "..."}     close the lid, then report the final measurement

Every command also has "v": 1, "cmd" and "expires_ts" (unix milliseconds).
"""

import json
from typing import Any

from .envelope import PROTOCOL_VERSION, EnvelopeError

COMMANDS = frozenset({"display", "unlock", "lock"})


def command(cmd: str, expires_ts: int, **fields: Any) -> bytes:
    if cmd not in COMMANDS:
        raise ValueError(f"unknown command {cmd!r}")
    return json.dumps(
        {"v": PROTOCOL_VERSION, "cmd": cmd, "expires_ts": expires_ts, **fields},
        separators=(",", ":"),
    ).encode()


def parse_command(payload: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(payload)
    except ValueError as e:
        raise EnvelopeError("command is not JSON") from e
    if not isinstance(obj, dict) or obj.get("v") != PROTOCOL_VERSION:
        raise EnvelopeError("bad command version")
    if obj.get("cmd") not in COMMANDS or not isinstance(obj.get("expires_ts"), int):
        raise EnvelopeError("bad command")
    return obj


def qr_payload(container_id: str, code: str) -> str:
    """What the container's display encodes as a QR code."""
    return f"zyrcle://c/{container_id}?code={code}"


def parse_qr(payload: str) -> tuple[str, str]:
    prefix = "zyrcle://c/"
    if not payload.startswith(prefix) or "?code=" not in payload:
        raise ValueError("not a Zyrcle container code")
    container_id, code = payload[len(prefix) :].split("?code=", 1)
    if not container_id or not code or "/" in container_id:
        raise ValueError("not a Zyrcle container code")
    return container_id, code

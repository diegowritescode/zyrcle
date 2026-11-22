"""MQTT topics.

Device to backend:  zyrcle/v1/devices/<device_id>/up/<type>      (signed envelopes)
Backend to device:  zyrcle/v1/devices/<device_id>/cmd             (commands, JSON)

The broker ACL lets each device publish only under its own .../up/ and read only its own .../cmd.
"""

PREFIX = "zyrcle/v1/devices"


def up_topic(device_id: str, message_type: str) -> str:
    return f"{PREFIX}/{device_id}/up/{message_type}"


def command_topic(device_id: str) -> str:
    return f"{PREFIX}/{device_id}/cmd"


def parse_up_topic(topic: str) -> tuple[str, str]:
    """Return (device_id, type) for an up topic, or raise ValueError."""
    parts = topic.split("/")
    if len(parts) != 6 or "/".join(parts[:3]) != PREFIX or parts[4] != "up":
        raise ValueError(f"not a device up topic: {topic}")
    return parts[3], parts[5]

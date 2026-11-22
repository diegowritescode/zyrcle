"""MQTT side of a simulated container: signs every message and obeys backend commands."""

import asyncio
import logging
import time
from typing import Any

import aiomqtt
from cryptography.hazmat.primitives.asymmetric import ec
from zyrcle_protocol import Envelope, EnvelopeError, command_topic, parse_command, seal, up_topic

from .container import SimulatedContainer

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class DeviceRunner:
    def __init__(
        self,
        container: SimulatedContainer,
        key: ec.EllipticCurvePrivateKey,
        host: str = "localhost",
        port: int = 1883,
        password: str | None = None,
        reading_interval_s: float = 0.5,
        settle_s: float = 0.2,
        seq_start: int | None = None,
    ):
        self.c = container
        self._key = key
        self._host, self._port, self._password = host, port, password
        self._interval = reading_interval_s
        self._settle = settle_s
        # Firmware keeps the counter in flash. Starting from the clock keeps it increasing across
        # simulator restarts without storage.
        self._seq = seq_start if seq_start is not None else time.time_ns() // 1000
        self._client: aiomqtt.Client | None = None
        self.connected = asyncio.Event()
        self.sent: list[bytes] = []  # every payload sent, for tests

    async def publish(self, message_type: str, body: dict[str, Any]) -> bytes:
        assert self._client is not None
        self._seq += 1
        payload = seal(
            self._key, Envelope(self.c.device_id, self._seq, _now_ms(), message_type, body)
        )
        await self._client.publish(up_topic(self.c.device_id, message_type), payload, qos=1)
        self.sent.append(payload)
        return payload

    async def run(self) -> None:
        async with aiomqtt.Client(
            self._host,
            self._port,
            username=self.c.device_id,
            password=self._password,
            identifier=f"sim-{self.c.device_id}",
        ) as client:
            self._client = client
            await client.subscribe(command_topic(self.c.device_id), qos=1)
            await self.publish("hello", {"fw": "zyrcle-sim/0.1", "area_mm2": self.c.area_mm2})
            self.connected.set()
            readings = asyncio.create_task(self._readings())
            try:
                async for message in client.messages:
                    await self._on_command(bytes(message.payload))
            finally:
                readings.cancel()
                self.connected.clear()

    async def _readings(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            s = self.c.session
            if s is not None:
                await self.publish(
                    "reading",
                    {
                        "session_id": s.session_id,
                        "weight_g": self.c.read_weight(),
                        "fill_mm": self.c.read_distance(),
                        "metal": self.c.metal_present(),
                    },
                )

    async def _on_command(self, payload: bytes) -> None:
        try:
            cmd = parse_command(payload)
        except EnvelopeError as e:
            log.warning("%s: ignoring bad command: %s", self.c.device_id, e)
            return
        if cmd["expires_ts"] < _now_ms():
            log.info("%s: ignoring expired %s", self.c.device_id, cmd["cmd"])
            return
        name = cmd["cmd"]
        if name == "display":
            self.c.code = str(cmd.get("code"))
        elif name == "unlock":
            if self.c.lid_open:
                log.info("%s: busy, ignoring unlock", self.c.device_id)
                return
            body = self.c.open_for(str(cmd["session_id"]))
            await self.publish("event", {"name": "lock_opened", **body})
        elif name == "lock":
            s = self.c.session
            if s is None or s.session_id != cmd.get("session_id"):
                return
            await self.publish("event", {"name": "lock_closing", "session_id": s.session_id})
            await asyncio.sleep(self._settle)  # let the scale settle before the final reading
            await self.publish("measurement", self.c.close())

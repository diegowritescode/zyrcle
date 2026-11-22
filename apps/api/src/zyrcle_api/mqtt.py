"""MQTT link between the API and the containers."""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

import aiomqtt
from zyrcle_protocol import command_topic

from .config import Settings

log = logging.getLogger(__name__)

MessageHandler = Callable[[str, bytes], Awaitable[None]]


class DeviceUnavailable(Exception):
    pass


class MqttBridge:
    def __init__(self, settings: Settings, handler: MessageHandler):
        self._settings = settings
        self._handler = handler
        self._client: aiomqtt.Client | None = None
        self.connected = asyncio.Event()

    async def run(self) -> None:
        s = self._settings
        topic = f"$share/{s.mqtt_share_group}/zyrcle/v1/devices/+/up/+"
        while True:
            try:
                async with aiomqtt.Client(
                    s.mqtt_host,
                    s.mqtt_port,
                    username=s.mqtt_username,
                    password=s.mqtt_password or None,
                    identifier=f"zyrcle-api-{uuid.uuid4().hex[:8]}",
                ) as client:
                    await client.subscribe(topic, qos=1)
                    self._client = client
                    self.connected.set()
                    log.info("mqtt connected to %s:%s", s.mqtt_host, s.mqtt_port)
                    async for message in client.messages:
                        try:
                            await self._handler(str(message.topic), bytes(message.payload))
                        except Exception:
                            log.exception("failed to handle message on %s", message.topic)
            except aiomqtt.MqttError as e:
                log.warning("mqtt connection lost (%s); retrying in 2 s", e)
            finally:
                self._client = None
                self.connected.clear()
            await asyncio.sleep(2)

    async def send(self, device_id: str, payload: bytes) -> None:
        if self._client is None:
            raise DeviceUnavailable("broker not connected")
        try:
            await self._client.publish(command_topic(device_id), payload, qos=1)
        except aiomqtt.MqttError as e:
            raise DeviceUnavailable(str(e)) from e

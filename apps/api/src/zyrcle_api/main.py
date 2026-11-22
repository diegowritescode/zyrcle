import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from .api import router
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker
from .live import LiveHub
from .mqtt import MqttBridge
from .sessions import SessionService

log = logging.getLogger(__name__)


async def _every(seconds: float, job, name: str) -> None:
    while True:
        try:
            await job()
        except Exception:
            log.exception("periodic job %s failed", name)
        await asyncio.sleep(seconds)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        maker = make_sessionmaker(engine)
        hub = LiveHub()
        holder: dict[str, SessionService] = {}

        async def on_message(topic: str, payload: bytes) -> None:
            await holder["service"].handle_device_message(topic, payload)

        bridge = MqttBridge(settings, on_message)
        service = SessionService(maker, settings, bridge, hub)
        holder["service"] = service
        app.state.settings, app.state.maker, app.state.hub = settings, maker, hub
        app.state.bridge, app.state.sessions = bridge, service

        tasks = [
            asyncio.create_task(bridge.run(), name="mqtt"),
            asyncio.create_task(_every(settings.sweep_interval_s, service.sweep, "sweep")),
            asyncio.create_task(
                _every(min(5.0, settings.code_rotation_s / 3), service.rotate_codes, "codes")
            ),
        ]
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with suppress(asyncio.CancelledError):
                    await t
            await engine.dispose()

    app = FastAPI(title="Zyrcle API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .chain import Chain, load_account_file
from .config import Settings, get_settings
from .db import make_engine, make_sessionmaker
from .live import LiveHub
from .mqtt import MqttBridge
from .payouts import PayoutWorker
from .public import router as public_router
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

        chain = None
        if settings.chain_enabled:
            chain = Chain(settings.chain_rpc_url, settings.treasury_address)  # type: ignore[arg-type]
        app.state.chain = chain
        app.state.simulator = (
            httpx.AsyncClient(base_url=settings.demo_simulator_url, timeout=5)
            if settings.demo_simulator_url
            else None
        )

        tasks = [
            asyncio.create_task(bridge.run(), name="mqtt"),
            asyncio.create_task(_every(settings.sweep_interval_s, service.sweep, "sweep")),
            asyncio.create_task(
                _every(min(5.0, settings.code_rotation_s / 3), service.rotate_codes, "codes")
            ),
        ]
        if chain is not None:
            worker = PayoutWorker(maker, chain, load_account_file(settings.oracle_key_file))  # type: ignore[arg-type]
            app.state.payouts = worker
            tasks.append(
                asyncio.create_task(_every(settings.payout_interval_s, worker.run_once, "payouts"))
            )
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with suppress(asyncio.CancelledError):
                    await t
            if app.state.simulator is not None:
                await app.state.simulator.aclose()
            await engine.dispose()

    app = FastAPI(title="Zyrcle API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    app.include_router(public_router)
    if settings.demo_simulator_url:
        from .demo import router as demo_router

        app.include_router(demo_router)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Authorization", "Content-Type"],
        )
    return app

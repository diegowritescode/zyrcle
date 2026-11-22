import asyncio
import os
import subprocess
import sys

import httpx
import pytest
from asgi_lifespan import LifespanManager
from zyrcle_protocol import generate_private_key, public_key_pem
from zyrcle_sim import DeviceRunner, SimulatedContainer

from zyrcle_api.config import Settings
from zyrcle_api.main import create_app

from .helpers import OPERATOR_TOKEN, OPS, sign_in, wait_for

DB_URL = os.environ.get(
    "ZYRCLE_TEST_DATABASE_URL", "postgresql+asyncpg://zyrcle:zyrcle@localhost:5432/zyrcle"
)
DEVICE_IDS = ["ctr-0001", "ctr-0002", "ctr-0003"]


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        database_url=DB_URL,
        mqtt_host=os.environ.get("ZYRCLE_TEST_MQTT_HOST", "localhost"),
        mqtt_password="dev-password",
        jwt_secret="test-secret-" + "y" * 32,
        operator_token=OPERATOR_TOKEN,
        siwe_domain="zyrcle.test",
        code_rotation_s=3,
        unlock_ack_timeout_s=3,
        idle_timeout_s=2,
        measurement_timeout_s=3,
        sweep_interval_s=0.2,
    )


@pytest.fixture(scope="session")
def migrated_db(settings: Settings) -> None:
    env = {**os.environ, "ZYRCLE_DATABASE_URL": settings.database_url}
    reset = (
        "import asyncio, sqlalchemy as sa\n"
        "from sqlalchemy.ext.asyncio import create_async_engine\n"
        "async def go():\n"
        f"    e = create_async_engine({settings.database_url!r})\n"
        "    async with e.begin() as c:\n"
        "        await c.execute(sa.text('drop schema public cascade'))\n"
        "        await c.execute(sa.text('create schema public'))\n"
        "    await e.dispose()\n"
        "asyncio.run(go())\n"
    )
    subprocess.run([sys.executable, "-c", reset], check=True, env=env)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)


@pytest.fixture(scope="session")
async def app(settings: Settings, migrated_db: None):
    application = create_app(settings)
    async with LifespanManager(application):
        await asyncio.wait_for(application.state.bridge.connected.wait(), 10)
        yield application


@pytest.fixture(scope="session")
async def client(app) -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture(scope="session")
async def devices(client: httpx.AsyncClient, settings: Settings) -> dict[str, DeviceRunner]:
    residence = (
        await client.post("/v1/operator/residences", json={"name": "Torres del Río"}, headers=OPS)
    ).json()
    runners: dict[str, DeviceRunner] = {}
    for device_id in DEVICE_IDS:
        key = generate_private_key()
        r = await client.post(
            "/v1/operator/devices",
            headers=OPS,
            json={"id": device_id, "public_key_pem": public_key_pem(key)},
        )
        assert r.status_code == 201, r.text
        r = await client.post(
            "/v1/operator/containers",
            headers=OPS,
            json={
                "id": device_id,
                "residence_id": residence["id"],
                "device_id": device_id,
                "name": f"Contenedor {device_id}",
                "accepted_materials": ["pet", "metal", "glass"],
                "area_mm2": 250_000,
                "depth_mm": 900,
            },
        )
        assert r.status_code == 201, r.text
        runners[device_id] = DeviceRunner(
            SimulatedContainer(device_id, seed=hash(device_id) % 1000),
            key,
            host=settings.mqtt_host,
            password="dev-password",
            reading_interval_s=0.1,
        )
    tasks = [asyncio.create_task(r.run()) for r in runners.values()]
    for r in runners.values():
        await asyncio.wait_for(r.connected.wait(), 10)
    await wait_for(lambda: all(r.c.code for r in runners.values()), timeout=10)
    yield runners
    for t in tasks:
        t.cancel()


@pytest.fixture(scope="session")
async def server_url(app) -> str:
    """The same app served by a real uvicorn on a free port (lifespan already running)."""
    import socket

    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, port=port, lifespan="off", log_level="warning"))
    task = asyncio.create_task(server.serve())
    await wait_for(lambda: server.started, timeout=5)
    yield f"127.0.0.1:{port}"
    server.should_exit = True
    await task


@pytest.fixture
async def resident(client: httpx.AsyncClient, settings: Settings) -> dict[str, str]:
    return await sign_in(client, settings)

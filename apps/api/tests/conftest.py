import asyncio
import os
import subprocess
import sys
import time

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


ANVIL_KEYS = {  # anvil's well-known development accounts
    "admin": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "operator": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "oracle": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
}
SEED_COP = 1_000_000


@pytest.fixture(scope="session")
def anvil() -> str:
    """A local EVM chain with ZyrcleChain's chain id. The NativeMinter mock is installed later."""
    import shutil
    import socket

    if shutil.which("anvil") is None:
        pytest.skip("anvil (Foundry) is not installed")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen(
        ["anvil", "--port", str(port), "--chain-id", "20261121", "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_rpc(url)
    except BaseException:
        proc.terminate()
        raise
    yield url
    proc.terminate()
    proc.wait(5)


def _wait_for_rpc(url: str) -> None:
    import json
    import urllib.request

    for _ in range(100):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}).encode()
            req = urllib.request.Request(url, body, {"content-type": "application/json"})
            urllib.request.urlopen(req, timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"anvil did not start at {url}")


@pytest.fixture(scope="session")
async def chain_env(anvil: str, tmp_path_factory) -> dict:
    """Deploy the Treasury with the backend's own code, enable minting, record seed capital."""
    import json
    import pathlib

    from zyrcle_api.chain import NATIVE_MINTER, Chain, load_account

    mock = json.loads(
        (pathlib.Path(__file__).parent / "fixtures" / "AnvilNativeMinter.json").read_text()
    )
    chain = Chain(anvil)
    await chain.w3.provider.make_request("anvil_setCode", [NATIVE_MINTER, mock["deployedBytecode"]])
    await chain.w3.provider.make_request("anvil_setBalance", [NATIVE_MINTER, hex(10**30)])
    admin, operator, oracle = (load_account(ANVIL_KEYS[k]) for k in ("admin", "operator", "oracle"))
    address = await chain.deploy_treasury(admin, operator.address, oracle.address)
    await chain.enable_minting(admin)
    await chain.record_seed_capital(operator, "test-seed", SEED_COP)
    # Residents' accounts; the oracle key doubles as the recovery guardian, as in local dev.
    factory = await chain.deploy_account_factory(admin, oracle.address)
    key_file = tmp_path_factory.mktemp("keys") / "oracle.key"
    key_file.write_text(ANVIL_KEYS["oracle"])
    operator_file = key_file.parent / "operator.key"
    operator_file.write_text(ANVIL_KEYS["operator"])
    yield {
        "rpc": anvil,
        "treasury": address,
        "factory": factory,
        "oracle_key_file": str(key_file),
        "operator_key_file": str(operator_file),
        "chain": chain,
    }
    await chain.w3.provider.disconnect()


SIM_RUNNERS: dict = {}  # filled by the devices fixture, served by the simulator control panel
DEMO_ORIGIN = "https://demo.zyrcle.test"


@pytest.fixture(scope="session")
async def simulator_control() -> str:
    import socket

    import uvicorn
    from zyrcle_sim.control import create_control_app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(
        uvicorn.Config(create_control_app(SIM_RUNNERS), port=port, log_level="warning")
    )
    task = asyncio.create_task(server.serve())
    await wait_for(lambda: server.started, timeout=5)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task


class FakeExpo:
    """Expo's push service, as far as the API uses it. Tokens containing "gone" are rejected at
    send time and tokens containing "uninstalled" in the receipt, both as DeviceNotRegistered."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.tickets: dict[str, str] = {}
        self.fail_next = 0
        self.url = ""

    def app(self):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        api = FastAPI()
        not_registered = {"status": "error", "details": {"error": "DeviceNotRegistered"}}

        @api.post("/send")
        async def send(request: Request):
            messages = await request.json()
            if self.fail_next:
                self.fail_next -= 1
                return JSONResponse({"errors": [{"code": "INTERNAL"}]}, status_code=503)
            tickets = []
            for m in messages:
                self.messages.append(m)
                if "gone" in m["to"]:
                    tickets.append({**not_registered, "message": "not registered"})
                else:
                    ticket = f"ticket-{len(self.tickets) + 1}"
                    self.tickets[ticket] = m["to"]
                    tickets.append({"status": "ok", "id": ticket})
            return {"data": tickets}

        @api.post("/getReceipts")
        async def receipts(request: Request):
            body = await request.json()
            return {
                "data": {
                    i: not_registered if "uninstalled" in self.tickets[i] else {"status": "ok"}
                    for i in body["ids"]
                    if i in self.tickets
                }
            }

        return api

    def to(self, token: str) -> list[dict]:
        return [m for m in self.messages if m["to"] == token]


@pytest.fixture(scope="session")
async def expo() -> FakeExpo:
    import socket

    import uvicorn

    fake = FakeExpo()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(fake.app(), port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    await wait_for(lambda: server.started, timeout=5)
    fake.url = f"http://127.0.0.1:{port}"
    yield fake
    server.should_exit = True
    await task


class FakeResend:
    """Resend's send-email endpoint. Addresses containing "bounce" are refused for good
    (validation_error); `fail_next` answers 503 that many times. Idempotency keys are honoured."""

    def __init__(self) -> None:
        self.emails: list[dict] = []
        self.by_key: dict[str, str] = {}
        self.fail_next = 0
        self.url = ""

    def app(self):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse

        api = FastAPI()

        @api.post("/emails")
        async def send(request: Request):
            if request.headers.get("authorization") != "Bearer re_test_key":
                return JSONResponse({"name": "validation_error"}, status_code=401)
            if not request.headers.get("user-agent"):
                return JSONResponse({"name": "missing_user_agent"}, status_code=403)
            if self.fail_next:
                self.fail_next -= 1
                return JSONResponse({"name": "service_unavailable"}, status_code=503)
            body = await request.json()
            if any("bounce" in to for to in body["to"]):
                return JSONResponse(
                    {"name": "validation_error", "message": "Invalid `to` field."},
                    status_code=422,
                )
            key = request.headers.get("idempotency-key", "")
            if key not in self.by_key:
                self.by_key[key] = f"email-{len(self.by_key) + 1}"
                self.emails.append(body)
            return {"id": self.by_key[key]}

        return api

    def to(self, address: str) -> list[dict]:
        return [e for e in self.emails if address in e["to"]]

    def last_code(self, address: str) -> str:
        import re

        mails = self.to(address)
        assert mails, f"no email to {address}"
        match = re.search(r"\b(\d{6})\b", mails[-1]["text"])
        assert match, mails[-1]["text"]
        return match.group(1)


@pytest.fixture(scope="session")
async def resend() -> FakeResend:
    import socket

    import uvicorn

    fake = FakeResend()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(fake.app(), port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    await wait_for(lambda: server.started, timeout=5)
    fake.url = f"http://127.0.0.1:{port}"
    yield fake
    server.should_exit = True
    await task


@pytest.fixture(scope="session")
def settings(
    chain_env: dict, simulator_control: str, expo: FakeExpo, resend: FakeResend
) -> Settings:
    return Settings(
        account_factory_address=chain_env["factory"],
        resend_api_url=resend.url,
        resend_api_key="re_test_key",
        email_interval_s=0.2,
        recovery_interval_s=0.2,
        expo_push_url=expo.url,
        notification_interval_s=0.2,
        push_receipt_delay_s=1,
        demo_simulator_url=simulator_control,
        cors_origins=DEMO_ORIGIN,
        chain_rpc_url=chain_env["rpc"],
        treasury_address=chain_env["treasury"],
        oracle_key_file=chain_env["oracle_key_file"],
        operator_key_file=chain_env["operator_key_file"],
        payout_interval_s=0.2,
        settlement_interval_s=0.2,
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
    host = (
        await client.post(
            "/v1/operator/hosts",
            json={"name": "Universidad del Río", "kind": "university"},
            headers=OPS,
        )
    ).json()
    site = (
        await client.post(
            "/v1/operator/sites",
            # Plenty of spots: every test signs in new residents, and each takes one per hour.
            json={"host_id": host["id"], "name": "Torres del Río", "slot_capacity": 1000},
            headers=OPS,
        )
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
                "site_id": site["id"],
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
    SIM_RUNNERS.update(runners)
    tasks = [asyncio.create_task(r.run()) for r in runners.values()]
    for r in runners.values():
        await asyncio.wait_for(r.connected.wait(), 10)
    await wait_for(lambda: all(r.c.code for r in runners.values()), timeout=10)
    # Reference prices for advances (test values, not market data).
    for material, price in (("pet", 1_000), ("metal", 4_000), ("glass", 200)):
        r = await client.put(
            f"/v1/operator/prices/{material}", headers=OPS, json={"cop_per_kg": price}
        )
        assert r.status_code == 200, r.text
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


# ---------------------------------------------------------------- collection (docs/adr/0012)

BIN = "ctr-0004"  # its own container, so other tests' deposits do not move its mass balance


@pytest.fixture(scope="session")
async def bin4(client, devices, settings) -> DeviceRunner:
    host = next(
        h for h in (await client.get("/v1/hosts")).json() if h["name"] == "Universidad del Río"
    )
    site = (
        await client.post(
            "/v1/operator/sites",
            headers=OPS,
            json={"host_id": host["id"], "name": "Campus de recolección", "slot_capacity": 1000},
        )
    ).json()
    key = generate_private_key()
    r = await client.post(
        "/v1/operator/devices", headers=OPS, json={"id": BIN, "public_key_pem": public_key_pem(key)}
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/v1/operator/containers",
        headers=OPS,
        json={
            "id": BIN,
            "site_id": site["id"],
            "device_id": BIN,
            "name": "Contenedor PET y HDPE",
            "accepted_materials": ["pet", "hdpe", "metal"],
            "area_mm2": 250_000,
            "depth_mm": 900,
        },
    )
    assert r.status_code == 201, r.text
    runner = DeviceRunner(
        SimulatedContainer(BIN, seed=4),
        key,
        host=settings.mqtt_host,
        password="dev-password",
        reading_interval_s=0.1,
    )
    SIM_RUNNERS[BIN] = runner
    task = asyncio.create_task(runner.run())
    await asyncio.wait_for(runner.connected.wait(), 10)
    await wait_for(lambda: runner.c.code is not None, timeout=10)
    for material in ("hdpe",):
        await client.put(f"/v1/operator/prices/{material}", headers=OPS, json={"cop_per_kg": 1000})
    yield runner
    task.cancel()


@pytest.fixture(scope="session")
async def collector(client, settings) -> dict:
    person = await sign_in(client, settings)
    r = await client.post(
        "/v1/operator/collectors",
        headers=OPS,
        json={"address": person["address"], "name": "Rosa Recicladora"},
    )
    assert r.status_code == 201, r.text
    return person

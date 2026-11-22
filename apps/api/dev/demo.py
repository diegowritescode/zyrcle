"""Walk through the deposit flow against a running API, with simulated containers.

    docker compose -f dev/compose.yml up -d && alembic upgrade head
    zyrcle-api serve            # in another terminal, with .env filled in
    python dev/demo.py

Scenarios: three PET bottles (verified), a stone declared as PET (sent to review), and a resident
who walks away without tapping "done" (closed by the idle timeout and still credited).
"""

import asyncio
import os
import uuid
from datetime import UTC, datetime

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from zyrcle_protocol import generate_private_key, public_key_pem, qr_payload
from zyrcle_sim import DeviceRunner, SimulatedContainer

from zyrcle_api.auth import build_siwe

API = os.environ.get("ZYRCLE_DEMO_API", "http://127.0.0.1:8000")
OPS = {"Authorization": f"Bearer {os.environ['ZYRCLE_OPERATOR_TOKEN']}"}
DOMAIN = os.environ.get("ZYRCLE_SIWE_DOMAIN", "localhost")
CHAIN_ID = int(os.environ.get("ZYRCLE_CHAIN_ID", "20261121"))


async def setup(api: httpx.AsyncClient) -> DeviceRunner:
    device_id = "ctr-0004"  # a dev broker account exists for ctr-0001..ctr-0004
    key = generate_private_key()
    host = (
        await api.post(
            "/v1/operator/hosts",
            headers=OPS,
            json={"name": f"Demo {uuid.uuid4().hex[:4]}", "kind": "university"},
        )
    ).json()
    site = (
        await api.post(
            "/v1/operator/sites", headers=OPS, json={"host_id": host["id"], "name": "Campus demo"}
        )
    ).json()
    r = await api.post(
        "/v1/operator/devices",
        headers=OPS,
        json={"id": device_id, "public_key_pem": public_key_pem(key)},
    )
    if r.status_code == 409:
        raise SystemExit("ctr-0004 is already registered: reset the dev database first")
    await api.post(
        "/v1/operator/containers",
        headers=OPS,
        json={
            "id": device_id,
            "site_id": site["id"],
            "device_id": device_id,
            "name": "Contenedor demo",
            "accepted_materials": ["pet", "metal"],
            "area_mm2": 250_000,
            "depth_mm": 900,
        },
    )
    return DeviceRunner(
        SimulatedContainer(device_id), key, password="dev-password", reading_interval_s=0.3
    )


async def sign_in(api: httpx.AsyncClient) -> dict[str, str]:
    account = Account.create()
    nonce = (await api.post("/v1/auth/nonce")).json()["nonce"]
    message = build_siwe(DOMAIN, account.address, CHAIN_ID, nonce, datetime.now(UTC))
    sig = account.sign_message(encode_defunct(text=message)).signature.hex()
    token = (await api.post("/v1/auth/verify", json={"message": message, "signature": sig})).json()
    print(f"resident {account.address} signed in")
    return {"Authorization": f"Bearer {token['token']}"}


async def until(api, auth, session_id, *states, timeout=90.0) -> dict:
    last = None
    for _ in range(int(timeout * 4)):
        s = (await api.get(f"/v1/sessions/{session_id}", headers=auth)).json()
        if s["state"] != last:
            print(f"    state: {s['state']}")
            last = s["state"]
        if s["state"] in states:
            return s
        await asyncio.sleep(0.25)
    raise SystemExit(f"timed out waiting for {states}")


async def scenario(api, auth, runner, title, material, items, finish=True) -> None:
    print(f"\n== {title}")
    qr = qr_payload(runner.c.device_id, runner.c.code or "")
    s = (await api.post("/v1/sessions", headers=auth, json={"qr": qr, "material": material})).json()
    await until(api, auth, s["id"], "open")
    for item, count in items:
        print(f"    deposits {count} x {item}")
        runner.c.deposit(item, count)
    await asyncio.sleep(1)
    if finish:
        await api.post(f"/v1/sessions/{s['id']}/finish", headers=auth)
    else:
        print("    walks away without tapping done")
    final = await until(api, auth, s["id"], "verified", "review", "empty")
    print(
        f"    result: {final['deposited_g']} g, score {final['score']}, {final['reasons'] or 'ok'}"
    )


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=10) as api:
        runner = await setup(api)
        task = asyncio.create_task(runner.run())
        await runner.connected.wait()
        while not runner.c.code:  # wait for the first access code from the backend
            await asyncio.sleep(0.2)
        print(f"container {runner.c.device_id} online, showing code {runner.c.code}")
        auth = await sign_in(api)
        await scenario(api, auth, runner, "Three PET bottles", "pet", [("pet_bottle", 3)])
        await scenario(api, auth, runner, "A stone declared as PET", "pet", [("stone", 1)])
        await scenario(
            api,
            auth,
            runner,
            "Cans, then the resident walks away",
            "metal",
            [("aluminum_can", 4)],
            finish=False,
        )
        task.cancel()


if __name__ == "__main__":
    asyncio.run(main())

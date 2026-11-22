"""Shared helpers for the end-to-end tests."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from zyrcle_sim import DeviceRunner

from zyrcle_api.auth import build_siwe
from zyrcle_api.config import Settings

OPERATOR_TOKEN = "operator-" + "x" * 32
OPS = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}


async def siwe(client: httpx.AsyncClient, settings: Settings, account) -> httpx.Response:
    """POST /v1/auth/verify for `account` (an eth_account key)."""
    nonce = (await client.post("/v1/auth/nonce")).json()["nonce"]
    message = build_siwe(
        settings.siwe_domain, account.address, settings.chain_id, nonce, datetime.now(UTC)
    )
    signature = account.sign_message(encode_defunct(text=message)).signature.hex()
    return await client.post("/v1/auth/verify", json={"message": message, "signature": signature})


async def sign_in(client: httpx.AsyncClient, settings: Settings, account=None) -> dict:
    """Sign in a phone key (a fresh one by default) with SIWE. Returns auth headers, the
    resident's account address (where their ZYR lives), the key, and the resident id."""
    account = account or Account.create()
    r = await siwe(client, settings, account)
    assert r.status_code == 200, r.text
    return {
        "Authorization": f"Bearer {r.json()['token']}",
        "address": r.json()["address"],
        "key": account,
        "id": r.json()["resident_id"],
    }


async def wait_for(predicate: Callable[[], bool | Awaitable[bool]], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("condition not met in time")


def headers(resident: dict) -> dict[str, str]:
    return {"Authorization": resident["Authorization"]}


def qr(runner: DeviceRunner) -> str:
    return f"zyrcle://c/{runner.c.device_id}?code={runner.c.code}"


async def state_of(client, resident, session_id: str) -> dict:
    r = await client.get(f"/v1/sessions/{session_id}", headers=headers(resident))
    assert r.status_code == 200, r.text
    return r.json()


async def wait_state(client, resident, session_id: str, *states: str, timeout=8.0) -> dict:
    holder: dict = {}

    async def reached() -> bool:
        holder["s"] = await state_of(client, resident, session_id)
        return holder["s"]["state"] in states

    await wait_for(reached, timeout)
    return holder["s"]

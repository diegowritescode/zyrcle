"""Deposits that end as ZYR in the resident's wallet: API + simulator + Treasury on anvil."""

import asyncio
import uuid

import pytest
from sqlalchemy import select

from zyrcle_api.chain import WEI_PER_COP
from zyrcle_api.models import Payout

from .conftest import SEED_COP
from .helpers import OPS, headers, qr, wait_for, wait_state

pytestmark = pytest.mark.integration


async def deposit(client, resident, runner, material, item, count, finish=True):
    # The code on the screen rotates every few seconds in tests; under load it can turn over between
    # reading it and posting it. A person would scan again, and so does the test.
    for _ in range(3):
        r = await client.post(
            "/v1/sessions", json={"qr": qr(runner), "material": material}, headers=headers(resident)
        )
        if not (r.status_code == 403 and "scan the container again" in r.text):
            break
        await asyncio.sleep(1)
    assert r.status_code == 201, r.text
    session = r.json()
    await wait_state(client, resident, session["id"], "open")
    runner.c.deposit(item, count)
    await wait_state(client, resident, session["id"], "depositing")
    if finish:
        await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    return session


async def payout_of(app, session_id: str) -> Payout | None:
    async with app.state.maker() as db:
        return await db.scalar(select(Payout).where(Payout.session_id == uuid.UUID(session_id)))


async def wait_payout(app, session_id: str, status: str = "confirmed") -> Payout:
    holder = {}

    async def done() -> bool:
        holder["p"] = await payout_of(app, session_id)
        return holder["p"] is not None and holder["p"].status == status

    await wait_for(done, timeout=10)
    return holder["p"]


async def test_a_verified_deposit_pays_its_advance_on_chain(
    app, client, devices, resident, chain_env
):
    session = await deposit(client, resident, devices["ctr-0001"], "pet", "pet_bottle", 40)
    final = await wait_state(client, resident, session["id"], "verified")
    expected = final["deposited_g"] * 1_000 * 5_000 // 10_000_000  # half of 1,000 COP/kg

    payout = await wait_payout(app, session["id"])
    assert payout.amount_cop == expected and payout.tx_hash
    balance = await chain_env["chain"].balance_wei(resident["address"])
    assert balance == expected * WEI_PER_COP

    me = (await client.get("/v1/me", headers=headers(resident))).json()
    assert me["balance_cop"] == expected
    assert me["payouts"][0]["status"] == "confirmed"


async def test_review_pays_only_when_approved(app, client, devices, resident, chain_env, settings):
    from .helpers import sign_in

    # A full water bottle is too dense for PET: review. The operator approves it.
    approved = await deposit(client, resident, devices["ctr-0002"], "pet", "full_water_bottle", 1)
    await wait_state(client, resident, approved["id"], "review")
    assert await payout_of(app, approved["id"]) is None
    await client.post(
        f"/v1/operator/sessions/{approved['id']}/review",
        headers=OPS,
        json={"approve": True, "note": "verified by hand"},
    )
    payout = await wait_payout(app, approved["id"])
    assert payout.amount_cop > 0

    # A stone is rejected: nothing is ever queued.
    other = await sign_in(client, settings)
    rejected = await deposit(client, other, devices["ctr-0002"], "pet", "stone", 1)
    await wait_state(client, other, rejected["id"], "review")
    await client.post(
        f"/v1/operator/sessions/{rejected['id']}/review", headers=OPS, json={"approve": False}
    )
    assert await payout_of(app, rejected["id"]) is None
    assert await chain_env["chain"].balance_wei(other["address"]) == 0


async def test_advances_are_capped_and_never_paid_twice(app, client, devices, resident, chain_env):
    # 40 cans at 4,000 COP/kg are worth ~1,200 COP: well under the cap, so raise the price.
    await client.put("/v1/operator/prices/metal", headers=OPS, json={"cop_per_kg": 900_000})
    session = await deposit(client, resident, devices["ctr-0003"], "metal", "aluminum_can", 40)
    await wait_state(client, resident, session["id"], "verified")
    payout = await wait_payout(app, session["id"])
    assert payout.amount_cop == 5_000  # the contract's per-deposit maximum
    await client.put("/v1/operator/prices/metal", headers=OPS, json={"cop_per_kg": 4_000})

    # Simulate a crash after the transaction was sent but before the row was updated.
    async with app.state.maker() as db:
        row = await db.get(Payout, payout.id)
        row.status = "pending"
        await db.commit()
    await app.state.payouts.run_once()
    again = await payout_of(app, session["id"])
    assert again.status == "confirmed"
    assert await chain_env["chain"].balance_wei(resident["address"]) == 5_000 * WEI_PER_COP


async def test_treasury_books_match_the_payouts(app, client, devices):
    state = (await client.get("/v1/operator/treasury", headers=OPS)).json()
    async with app.state.maker() as db:
        confirmed = sum(
            p.amount_cop
            for p in await db.scalars(select(Payout).where(Payout.status == "confirmed"))
        )
    assert state["seed_capital_cop"] == SEED_COP
    assert state["minted_cop"] == confirmed
    assert state["minted_cop"] <= state["backing_cop"]


async def test_me_still_answers_when_the_chain_is_unreachable(app, client, resident, monkeypatch):
    async def down(address):
        raise ConnectionError("rpc unreachable")

    monkeypatch.setattr(app.state.chain, "balance_wei", down)
    r = await client.get("/v1/me", headers=headers(resident))
    assert r.status_code == 200 and r.json()["balance_cop"] is None

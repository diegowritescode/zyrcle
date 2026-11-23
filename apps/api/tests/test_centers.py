"""Collection centers and their prices (docs/adr/0037)."""

import uuid

import pytest
from sqlalchemy import select

from zyrcle_api.models import Container, Payout
from zyrcle_api.pricing import advance_cop

from .helpers import OPS, sign_in, wait_state
from .test_chain_e2e import deposit

pytestmark = pytest.mark.integration


async def bin_site(app, device_id: str) -> str:
    async with app.state.maker() as db:
        site = await db.scalar(select(Container.site_id).where(Container.device_id == device_id))
        return str(site)


async def new_center(client, name: str | None = None) -> dict:
    r = await client.post(
        "/v1/operator/centers",
        headers=OPS,
        json={"name": name or f"Centro {uuid.uuid4().hex[:6]}", "tax_id": "900111222-3"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_centers_hold_a_price_per_material_and_the_sites_that_sell_to_them(app, client, bin4):
    center = await new_center(client)
    again = await client.post("/v1/operator/centers", headers=OPS, json={"name": center["name"]})
    assert again.status_code == 409
    bad = await client.put(
        f"/v1/operator/centers/{center['id']}/prices/gold", headers=OPS, json={"cop_per_kg": 1}
    )
    assert bad.status_code == 422
    r = await client.put(
        f"/v1/operator/centers/{center['id']}/prices/pet", headers=OPS, json={"cop_per_kg": 2_400}
    )
    assert r.status_code == 200
    assert r.json()["prices"]["pet"]["cop_per_kg"] == 2_400
    assert r.json()["prices"]["pet"]["updated_by"] == "token"
    site = {"id": await bin_site(app, "ctr-0004")}
    r = await client.put(
        f"/v1/operator/sites/{site['id']}/center", headers=OPS, json={"center_id": center["id"]}
    )
    assert r.status_code == 200
    listed = {c["id"]: c for c in (await client.get("/v1/operator/centers", headers=OPS)).json()}
    assert site["id"] in {s["id"] for s in listed[center["id"]]["sites"]}
    unset = {"center_id": None}
    await client.put(f"/v1/operator/sites/{site['id']}/center", headers=OPS, json=unset)
    assert (await client.get("/v1/operator/centers")).status_code == 401


async def test_the_advance_follows_the_price_of_the_center_the_site_sells_to(
    app, client, settings, devices
):
    # A demo container, not the collection tests' one: this deposit is never collected.
    runner = devices["ctr-0001"]
    center = await new_center(client)
    await client.put(
        f"/v1/operator/centers/{center['id']}/prices/pet", headers=OPS, json={"cop_per_kg": 3_900}
    )
    site_id = await bin_site(app, "ctr-0001")
    await client.put(
        f"/v1/operator/sites/{site_id}/center", headers=OPS, json={"center_id": center["id"]}
    )
    try:
        person = await sign_in(client, settings)
        s = await deposit(client, person, runner, "pet", "pet_bottle", 3)
        done = await wait_state(client, person, s["id"], "verified")
        async with app.state.maker() as db:
            payout = await db.scalar(select(Payout).where(Payout.session_id == uuid.UUID(s["id"])))
        assert payout is not None
        expected = advance_cop(
            done["deposited_g"], 3_900, settings.advance_ratio_bps, settings.max_advance_cop
        )
        assert payout.amount_cop == expected
    finally:
        await client.put(
            f"/v1/operator/sites/{site_id}/center", headers=OPS, json={"center_id": None}
        )

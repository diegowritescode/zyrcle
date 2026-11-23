"""Collections: a collector empties a container into bags, weighed by its own scale (ADR 0012).

These tests use their own container, ctr-0004, so the deposits of other tests do not move its
mass balance. They run in order: the second starts from what the first left inside.
"""

import asyncio

import pytest
from sqlalchemy import select
from zyrcle_protocol import generate_private_key, public_key_pem
from zyrcle_sim import DeviceRunner, SimulatedContainer

from zyrcle_api.models import DepositSession

from .conftest import SIM_RUNNERS
from .helpers import OPS, headers, qr, sign_in, wait_for, wait_state
from .test_chain_e2e import deposit

pytestmark = pytest.mark.integration

BIN = "ctr-0004"


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


async def bags(client, material: str, count: int = 1) -> list[dict]:
    r = await client.post(
        "/v1/operator/bags", headers=OPS, json={"material": material, "count": count}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def collection(client, person, collection_id: str) -> dict:
    r = await client.get(f"/v1/collections/{collection_id}", headers=headers(person))
    assert r.status_code == 200, r.text
    return r.json()


async def wait_collection(client, person, collection_id: str, check, timeout=8.0) -> dict:
    holder: dict = {}

    async def ok() -> bool:
        holder["c"] = await collection(client, person, collection_id)
        return check(holder["c"])

    await wait_for(ok, timeout)
    return holder["c"]


async def take(client, person, c: dict, bag: dict | None, kind: str | None) -> dict:
    """Scan `bag` (None: residue), take `kind` out of the container, wait for the scale, done."""
    r = await client.post(
        f"/v1/collections/{c['id']}/fills",
        headers=headers(person),
        json={"bag": bag["qr"] if bag else None},
    )
    assert r.status_code == 201, r.text
    fill_id = r.json()["open_fill_id"]
    before = r.json()["weight_g"]
    r = await client.post(
        f"/v1/demo/collections/{c['id']}/take-out", headers=headers(person), json={"kind": kind}
    )
    assert r.status_code == 200, r.text
    taken = r.json()["grams"]
    if taken:
        await wait_collection(
            client, person, c["id"], lambda x: x["weight_g"] <= before - taken + 10
        )
    r = await client.post(
        f"/v1/collections/{c['id']}/fills/{fill_id}/done", headers=headers(person)
    )
    assert r.status_code == 200, r.text
    return next(f for f in r.json()["fills"] if f["id"] == fill_id)


async def open_collection(client, person, runner) -> dict:
    r = await client.post("/v1/collections", headers=headers(person), json={"qr": qr(runner)})
    assert r.status_code == 201, r.text
    return await wait_collection(
        client, person, r.json()["id"], lambda x: x["state"] == "open" and x["weight_g"]
    )


async def incidents(client, collection_id: str) -> list[dict]:
    r = await client.get("/v1/operator/incidents?status=open", headers=OPS)
    return [i for i in r.json() if i["collection_id"] == collection_id]


async def test_a_collector_empties_a_container_into_weighed_bags(
    app, client, settings, bin4, collector, resident
):
    neighbor = await sign_in(client, settings)
    pet = await deposit(client, resident, bin4, "pet", "pet_bottle", 4)
    await wait_state(client, resident, pet["id"], "verified")
    hdpe = await deposit(client, resident, bin4, "hdpe", "hdpe_jug", 2)
    await wait_state(client, resident, hdpe["id"], "verified")
    stone = await deposit(client, neighbor, bin4, "pet", "stone", 1)
    await wait_state(client, neighbor, stone["id"], "review")
    pet_bag, hdpe_bag = (await bags(client, "pet"))[0], (await bags(client, "hdpe"))[0]

    home = (await client.get("/v1/collector", headers=headers(collector))).json()
    assert home["name"] == "Rosa Recicladora" and home["current"] is None
    me = (await client.get("/v1/me", headers=headers(collector))).json()
    assert me["collector"] == "Rosa Recicladora"
    assert (await client.get("/v1/collector", headers=headers(resident))).status_code == 403
    r = await client.post("/v1/collections", headers=headers(resident), json={"qr": qr(bin4)})
    assert r.status_code == 403  # only collectors empty containers

    c = await open_collection(client, collector, bin4)
    # Never collected: it should weigh the first deposit's tare plus what every deposit added.
    assert c["expected_g"] is not None and abs(c["expected_g"] - c["tare_g"]) <= 50
    assert await incidents(client, c["id"]) == []
    # Nobody deposits while the container is being emptied.
    r = await client.post(
        "/v1/sessions", headers=headers(resident), json={"qr": qr(bin4), "material": "pet"}
    )
    assert r.status_code == 409

    pet_fill = await take(client, collector, c, pet_bag, "pet")
    assert pet_fill["bag_code"] == pet_bag["code"] and 90 <= pet_fill["grams"] <= 110
    hdpe_fill = await take(client, collector, c, hdpe_bag, "hdpe")
    assert 110 <= hdpe_fill["grams"] <= 130
    residue = await take(client, collector, c, None, None)  # the stone and what was there before
    assert residue["residue"] and 5_950 <= residue["grams"] <= 6_050

    r = await client.post(f"/v1/collections/{c['id']}/finish", headers=headers(collector))
    assert r.status_code == 200, r.text
    done = await wait_collection(client, collector, c["id"], lambda x: x["state"] == "closed")
    assert abs(done["removed_g"] - sum(f["grams"] for f in done["fills"])) <= 50
    assert abs(done["final_g"]) <= 20  # empty
    assert await incidents(client, c["id"]) == []

    async with app.state.maker() as db:
        linked = dict(
            (
                await db.execute(
                    select(DepositSession.id, DepositSession.collection_id).where(
                        DepositSession.id.in_([pet["id"], hdpe["id"], stone["id"]])
                    )
                )
            ).all()
        )
    # Every deposit whose material left is traced to this collection, paid or still in review.
    assert {str(v) for v in linked.values()} == {c["id"]}

    r = await client.post(f"/v1/bags/{pet_bag['code']}/seal", headers=headers(collector))
    assert r.status_code == 200 and r.json()["status"] == "sealed"
    assert 90 <= r.json()["grams"] <= 110
    home = (await client.get("/v1/collector", headers=headers(collector))).json()
    assert {b["code"]: b["status"] for b in home["bags"]} == {
        pet_bag["code"]: "sealed",
        hdpe_bag["code"]: "open",
    }


async def test_material_that_skips_the_scale_opens_incidents(client, settings, bin4, collector):
    neighbor = await sign_in(client, settings)
    session = await deposit(client, neighbor, bin4, "pet", "pet_bottle", 8)
    await wait_state(client, neighbor, session["id"], "verified")
    bin4.c._grams["rock"] += 500  # half a kilo pushed in without a session: tampering
    bag = (await bags(client, "pet"))[0]

    c = await open_collection(client, collector, bin4)
    [container_incident] = await incidents(client, c["id"])
    assert container_incident["kind"] == "container_balance"
    assert 450 <= container_incident["difference_g"] <= 550

    await take(client, collector, c, bag, "pet")
    # The rest leaves without being weighed into a bag or residue.
    r = await client.post(
        f"/v1/demo/collections/{c['id']}/take-out", headers=headers(collector), json={"kind": None}
    )
    assert r.status_code == 200
    await asyncio.sleep(0.3)
    await client.post(f"/v1/collections/{c['id']}/finish", headers=headers(collector))
    await wait_collection(client, collector, c["id"], lambda x: x["state"] == "closed")

    found = {i["kind"]: i for i in await incidents(client, c["id"])}
    assert set(found) == {"container_balance", "collection_balance"}
    # Both name the bag filled from this container: it cannot be sold until they are resolved.
    assert found["container_balance"]["bag_ids"] == [bag["id"]]
    assert found["collection_balance"]["bag_ids"] == [bag["id"]]

    r = await client.post(
        f"/v1/operator/incidents/{found['container_balance']['id']}/resolve",
        headers=OPS,
        json={"note": "Someone forced the lid; the extra PET was weighed and is fine."},
    )
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert [i["kind"] for i in await incidents(client, c["id"])] == ["collection_balance"]


async def test_bags_belong_to_one_collector_and_one_material(client, settings, bin4, collector):
    other = await sign_in(client, settings)
    await client.post(
        "/v1/operator/collectors", headers=OPS, json={"address": other["address"], "name": "Luis"}
    )
    metal, glass = (await bags(client, "metal"))[0], (await bags(client, "glass"))[0]

    c = await open_collection(client, collector, bin4)
    r = await client.post(
        f"/v1/collections/{c['id']}/fills", headers=headers(collector), json={"bag": glass["code"]}
    )
    assert r.status_code == 422  # this container holds no glass
    r = await client.post(
        f"/v1/collections/{c['id']}/fills", headers=headers(collector), json={"bag": "nonsense"}
    )
    assert r.status_code == 422
    await take(client, collector, c, metal, "metal")  # nothing of it inside: an empty fill
    r = await client.post(
        f"/v1/collections/{c['id']}/fills", headers=headers(other), json={"bag": metal["code"]}
    )
    assert r.status_code == 404  # not their collection
    await client.post(f"/v1/collections/{c['id']}/finish", headers=headers(collector))
    await wait_collection(client, collector, c["id"], lambda x: x["state"] == "closed")

    r = await client.post(f"/v1/bags/{metal['code']}/seal", headers=headers(collector))
    assert r.status_code == 409  # an empty bag is not sealed
    r = await client.post(f"/v1/bags/{metal['code']}/seal", headers=headers(other))
    assert r.status_code == 404

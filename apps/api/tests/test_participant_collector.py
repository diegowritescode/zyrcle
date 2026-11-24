"""Block 4: where to spend (docs/adr/0041), fill alerts and a collector's host (docs/adr/0042).

The deposit steps, the personal impact and the collector's earnings follow a real sale in
test_sale, from the deposit to the settlement on chain.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from zyrcle_api.collector_views import split
from zyrcle_api.fill import alert_if_full, fill_pct
from zyrcle_api.models import Collection, Collector, Container, Host, Notification

from .helpers import OPS, headers, sign_in


def test_fill_level_from_the_distance_sensor():
    assert fill_pct(900, 900) == 0  # the sensor sees the bottom
    assert fill_pct(900, 90) == 90
    assert fill_pct(900, 0) == 100
    assert fill_pct(900, 1_000) == 0  # noise below the bottom
    assert fill_pct(900, None) is None


def test_a_share_split_among_collections_adds_up_exactly():
    assert split(4_500, [1, 1, 1]) == [1_500, 1_500, 1_500]
    assert sum(split(1_000, [3, 3, 3])) == 1_000
    assert split(10, [1, 0]) == [10, 0]
    assert split(0, [5, 5]) == [0, 0] and split(7, [0, 0]) == [0, 0]


@pytest.mark.integration
async def test_a_full_container_pushes_its_hosts_collectors_once_per_fill_cycle(
    app, client, devices, settings
):
    anyone, elsewhere = await sign_in(client, settings), await sign_in(client, settings)
    now = datetime.now(UTC)
    async with app.state.maker() as db:  # never committed: the rows vanish with the transaction
        other = Host(id=uuid.uuid4(), name="Otra universidad", kind="university", created_at=now)
        db.add(other)
        await db.flush()
        db.add(Collector(resident_id=uuid.UUID(anyone["id"]), name="Para todos"))
        db.add(Collector(resident_id=uuid.UUID(elsewhere["id"]), name="De otra", host_id=other.id))
        await db.flush()
        container = await db.get(Container, "ctr-0003")
        assert container is not None
        near_top = container.depth_mm // 10  # 90 %

        async def alerted() -> dict[str, int]:
            rows = await db.scalars(
                select(Notification.resident_id).where(
                    Notification.kind == "container_full",
                    Notification.resident_id.in_(
                        [uuid.UUID(anyone["id"]), uuid.UUID(elsewhere["id"])]
                    ),
                )
            )
            counts: dict[str, int] = {}
            for r in rows:
                counts[str(r)] = counts.get(str(r), 0) + 1
            return counts

        half = container.depth_mm // 2
        assert await alert_if_full(db, container, half, 80, now) == 0
        assert await alerted() == {}
        await alert_if_full(db, container, near_top, 80, now)
        assert await alerted() == {anyone["id"]: 1}  # not the other host's collector
        await alert_if_full(db, container, near_top - 5, 80, now)
        assert await alerted() == {anyone["id"]: 1}  # once per fill cycle

        db.add(
            Collection(
                id=uuid.uuid4(),
                container_id=container.id,
                collector_id=uuid.UUID(anyone["id"]),
                state="closed",
                closed_at=now,
                created_at=now,
                updated_at=now,
                last_activity_at=now,
            )
        )
        await db.flush()
        await alert_if_full(db, container, near_top, 80, now)
        assert await alerted() == {anyone["id"]: 2}  # emptied, then full again
        title = await db.scalar(
            select(Notification.title).where(
                Notification.kind == "container_full",
                Notification.resident_id == uuid.UUID(anyone["id"]),
            )
        )
        assert title == f"{container.name} está al 90 %"
        await db.rollback()


@pytest.mark.integration
async def test_participants_find_campus_merchants_without_their_tax_id(client, devices, settings):
    host = next(
        h for h in (await client.get("/v1/hosts")).json() if h["name"] == "Universidad del Río"
    )
    site = host["sites"][0]
    person = await sign_in(client, settings)
    shop = {
        "address": person["address"],
        "name": "Cafetería El Roble",
        "nit": "900123456-7",
        "host_id": host["id"],
        "site_id": site["id"],
        "place": "Bloque 7, primer piso",
        "hours": "L-V 7:00 a 18:00",
        "offer": "Café, almuerzos y papelería",
    }
    r = await client.post("/v1/operator/merchants", headers=OPS, json=shop)
    assert r.status_code == 201, r.text
    assert r.json()["place"] == "Bloque 7, primer piso" and r.json()["site_id"] == site["id"]

    listed = [m for m in (await client.get("/v1/merchants")).json() if m["name"] == shop["name"]]
    assert listed == [
        {
            "name": "Cafetería El Roble",
            "host": {"id": host["id"], "name": "Universidad del Río"},
            "site": {"id": site["id"], "name": site["name"]},
            "place": "Bloque 7, primer piso",
            "hours": "L-V 7:00 a 18:00",
            "offer": "Café, almuerzos y papelería",
        }
    ]

    r = await client.post("/v1/operator/merchants", headers=OPS, json={**shop, "host_id": None})
    assert r.status_code == 422  # a site, but not of the merchant's host
    r = await client.post(
        "/v1/operator/merchants", headers=OPS, json={**shop, "active": False, "place": "  "}
    )
    assert r.status_code == 201 and r.json()["place"] is None
    assert shop["name"] not in {m["name"] for m in (await client.get("/v1/merchants")).json()}


@pytest.mark.integration
async def test_a_collector_of_one_host_sees_only_its_containers(client, devices, settings):
    hosts = (await client.get("/v1/hosts")).json()
    host = next(h for h in hosts if h["name"] == "Universidad del Río")
    person = await sign_in(client, settings)
    body = {"address": person["address"], "name": "Luis", "host_id": str(uuid.uuid4())}
    r = await client.post("/v1/operator/collectors", headers=OPS, json=body)
    assert r.status_code == 404
    r = await client.post(
        "/v1/operator/collectors", headers=OPS, json={**body, "host_id": host["id"]}
    )
    assert r.status_code == 201 and r.json()["host_id"] == host["id"]

    home = (await client.get("/v1/collector", headers=headers(person))).json()
    sites = {s["id"] for s in host["sites"]}
    assert home["containers"] and all(c["site"]["id"] in sites for c in home["containers"])
    levels = [c["fill_pct"] for c in home["containers"] if c["fill_pct"] is not None]
    assert levels == sorted(levels, reverse=True)  # fullest first
    earned = (await client.get("/v1/collector/earnings", headers=headers(person))).json()
    assert earned["collections"] == [] and earned["total_cop"] == 0
    assert len(earned["months"]) == 6
    stranger = await sign_in(client, settings)
    r = await client.get("/v1/collector/earnings", headers=headers(stranger))
    assert r.status_code == 403

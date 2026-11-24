"""Sales: a bag sold, the money seen in the bank, everyone settled on chain (docs/adr/0013).

Uses the collection container (ctr-0004) and runs after test_collection, starting from what it left.
"""

import uuid
from datetime import date

import pytest
from eth_account import Account
from sqlalchemy import select

from zyrcle_api.chain import WEI_PER_COP
from zyrcle_api.domain.impact import co2e_g
from zyrcle_api.models import Notification

from .collecting import bags, incidents, open_collection, take, wait_collection
from .conftest import BIN
from .helpers import OPS, headers, sign_in, wait_for, wait_state
from .test_centers import new_center
from .test_chain_e2e import deposit, wait_payout

pytestmark = pytest.mark.integration


async def fill_and_seal(client, collector, runner, kind: str) -> dict:
    """Empty `runner` into one bag of `kind` (and the rest as residue), then seal the bag."""
    bag = (await bags(client, kind))[0]
    c = await open_collection(client, collector, runner)
    await take(client, collector, c, bag, kind)
    await take(client, collector, c, None, None)
    await client.post(f"/v1/collections/{c['id']}/finish", headers=headers(collector))
    await wait_collection(client, collector, c["id"], lambda x: x["state"] == "closed")
    r = await client.post(f"/v1/bags/{bag['code']}/seal", headers=headers(collector))
    assert r.status_code == 200, r.text
    assert await incidents(client, c["id"]) == []
    return r.json()


async def steps_of(client, person, session_id: str) -> list[dict]:
    history = (await client.get("/v1/me", headers=headers(person))).json()["sessions"]
    return next(h for h in history if h["id"] == session_id)["steps"]


async def sale_of(client, sale_id: str) -> dict:
    r = await client.get(f"/v1/operator/sales/{sale_id}", headers=OPS)
    assert r.status_code == 200, r.text
    return r.json()


async def wait_line(client, sale_id: str, *statuses: str, timeout: float = 20.0) -> dict:
    holder: dict = {}

    async def reached() -> bool:
        holder["s"] = await sale_of(client, sale_id)
        return holder["s"]["lines"][0]["status"] in statuses

    await wait_for(reached, timeout)
    return holder["s"]


async def balance(chain, address: str) -> int:
    return await chain.balance_wei(address) // WEI_PER_COP


async def host_with_address(client) -> tuple[dict, str]:
    host = next(
        h for h in (await client.get("/v1/hosts")).json() if h["name"] == "Universidad del Río"
    )
    address = Account.create().address
    r = await client.patch(
        f"/v1/operator/hosts/{host['id']}", headers=OPS, json={"payout_address": address}
    )
    assert r.status_code == 200 and r.json()["payout_address"] == address.lower()
    return host, address


async def test_a_sold_bag_pays_residents_collector_and_host_from_the_buyer(
    app, client, settings, chain_env, bin4, collector
):
    chain = chain_env["chain"]
    ana, beto = await sign_in(client, settings), await sign_in(client, settings)
    a = await deposit(client, ana, bin4, "pet", "pet_bottle", 8)  # 200 g
    await wait_state(client, ana, a["id"], "verified")
    b = await deposit(client, beto, bin4, "pet", "pet_bottle", 4)  # 100 g
    await wait_state(client, beto, b["id"], "verified")
    advance_a = (await wait_payout(app, a["id"])).amount_cop
    advance_b = (await wait_payout(app, b["id"])).amount_cop
    bag = await fill_and_seal(client, collector, bin4, "pet")
    _, host_address = await host_with_address(client)

    r = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={
            "buyer": "Centro de acopio La 80",
            "ticket_ref": "T-1001",
            "sold_on": "2026-11-22",
            "lines": [{"bag": bag["qr"], "buyer_g": bag["grams"] - 10, "amount_cop": 30_000}],
        },
    )
    assert r.status_code == 201, r.text
    sale = r.json()
    assert sale["status"] == "recorded" and sale["total_cop"] == 30_000
    assert sale["evidence_hash"].startswith("0x") and len(sale["evidence_hash"]) == 66
    r = await client.post(
        "/v1/operator/sales", headers=OPS, json={**sale_payload(bag), "ticket_ref": "T-1002"}
    )
    assert r.status_code == 409  # a bag is sold once
    # Both participants hear their material was sold, once (docs/adr/0041), and see where it is.
    async with app.state.maker() as db:
        sold = list(
            await db.scalars(
                select(Notification.resident_id).where(
                    Notification.kind == "deposit_sold",
                    Notification.resident_id.in_([uuid.UUID(ana["id"]), uuid.UUID(beto["id"])]),
                )
            )
        )
    assert sorted(map(str, sold)) == sorted([ana["id"], beto["id"]])
    steps = await steps_of(client, ana, a["id"])
    keys = ["deposited", "verified", "advance", "collected", "sold", "paid"]
    assert [s["key"] for s in steps] == keys
    assert [s["status"] for s in steps] == ["done"] * 5 + ["pending"]
    assert steps[2]["amount_cop"] == advance_a and steps[2]["tx_hash"]
    assert steps[4]["note"] == "Centro de acopio La 80" and steps[4]["at"].startswith("2026-11-22")

    before = {
        "ana": await balance(chain, ana["address"]),
        "beto": await balance(chain, beto["address"]),
        "collector": await balance(chain, collector["address"]),
        "host": await balance(chain, host_address),
    }
    line_id = sale["lines"][0]["id"]
    assert not (await chain.sale(uuid.UUID(line_id))).recorded  # nothing on chain before the bank

    r = await client.post(
        f"/v1/operator/sales/{sale['id']}/confirm",
        headers=OPS,
        json={"bank_ref": "BANCO-778", "received_cop": 29_000},
    )
    assert r.status_code == 422  # the bank must have received exactly what the ticket says
    r = await client.post(
        f"/v1/operator/sales/{sale['id']}/confirm",
        headers=OPS,
        json={"bank_ref": "BANCO-778", "received_cop": 30_000},
    )
    assert r.status_code == 200 and r.json()["status"] == "confirmed"

    done = await wait_line(client, sale["id"], "settled", "failed")
    line = done["lines"][0]
    assert line["status"] == "settled", line["reason"]
    # 65 % residents, 15 % collector, 10 % host: 19,500 / 4,500 / 3,000. The residents' part is
    # split by verified grams, each rounded down, so a peso of dust may stay unminted.
    grams_a = (await wait_state(client, ana, a["id"], "verified"))["deposited_g"]
    grams_b = (await wait_state(client, beto, b["id"], "verified"))["deposited_g"]
    expected_a = 19_500 * grams_a // (grams_a + grams_b)
    expected_b = 19_500 * grams_b // (grams_a + grams_b)
    assert (line["collector_cop"], line["host_cop"]) == (4_500, 3_000)
    assert line["residents_cop"] == expected_a + expected_b >= 19_498
    assert [t["step"] for t in line["txs"]] == [
        "recordSale",
        "settleResidents",
        "payCollector",
        "payHost",
    ]
    report = {(s["party"], s["ref"]): s for s in line["settlements"]}
    share_a, share_b = report[("deposit", a["id"])], report[("deposit", b["id"])]
    assert (share_a["share_cop"], share_b["share_cop"]) == (expected_a, expected_b)
    assert share_a["paid_cop"] == expected_a - advance_a
    assert share_b["paid_cop"] == expected_b - advance_b

    assert await balance(chain, ana["address"]) - before["ana"] == expected_a - advance_a
    assert await balance(chain, beto["address"]) - before["beto"] == expected_b - advance_b
    assert await balance(chain, collector["address"]) - before["collector"] == 4_500
    assert await balance(chain, host_address) - before["host"] == 3_000
    state = await chain.state()
    assert state.minted_cop <= state.backing_cop
    history = (await client.get("/v1/me", headers=headers(ana))).json()["sessions"]
    assert next(h for h in history if h["id"] == a["id"])["settled_cop"] == expected_a - advance_a
    paid = (await steps_of(client, ana, a["id"]))[5]
    assert paid["status"] == "done" and paid["tx_hash"]
    assert (paid["share_cop"], paid["amount_cop"]) == (expected_a, expected_a - advance_a)

    # Her impact counts the sold grams, with the certificates' factors (docs/adr/0027, 0041).
    impact = (await client.get("/v1/me/impact", headers=headers(ana))).json()
    pet = {"verified_g": grams_a, "sold_g": grams_a, "co2e_g": co2e_g("pet", grams_a)}
    assert impact["totals"] == pet
    assert impact["materials"] == [{"material": "pet", **pet}]
    assert impact["months"][-1]["sold_g"] == grams_a and len(impact["months"]) == 12

    # The collector sees what that collection paid, and the emptied container (docs/adr/0042).
    earned = (await client.get("/v1/collector/earnings", headers=headers(collector))).json()
    assert any(c["earned_cop"] == 4_500 and c["pending_g"] == 0 for c in earned["collections"])
    assert earned["months"][-1]["earned_cop"] >= 4_500
    home = (await client.get("/v1/collector", headers=headers(collector))).json()
    emptied = next(c for c in home["containers"] if c["id"] == BIN)
    assert emptied["last_emptied_at"] and emptied["deposits_since"] == 0
    assert emptied["fill_pct"] is not None and emptied["fill_pct"] <= 10

    bags_now = (await client.get("/v1/operator/bags?status=settled", headers=OPS)).json()
    assert bag["code"] in {b["code"] for b in bags_now}
    async with app.state.maker() as db:
        kinds = set(
            await db.scalars(
                select(Notification.kind).where(Notification.resident_id == uuid.UUID(ana["id"]))
            )
        )
    assert "settlement_paid" in kinds


def sale_payload(bag: dict) -> dict:
    return {
        "buyer": "Centro de acopio La 80",
        "ticket_ref": "T-x",
        "sold_on": "2026-11-22",
        "lines": [{"bag": bag["code"], "buyer_g": bag["grams"], "amount_cop": 1_000}],
    }


async def test_a_bag_the_buyer_weighs_differently_waits_for_the_operator(
    client, settings, chain_env, bin4, collector
):
    person = await sign_in(client, settings)
    s = await deposit(client, person, bin4, "pet", "pet_bottle", 10)  # 250 g
    await wait_state(client, person, s["id"], "verified")
    bag = await fill_and_seal(client, collector, bin4, "pet")
    await host_with_address(client)

    r = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={
            **sale_payload(bag),
            "lines": [{"bag": bag["code"], "buyer_g": 900, "amount_cop": 5_000}],
        },
    )
    assert r.status_code == 201, r.text
    sale = r.json()
    incident = next(
        i
        for i in (await client.get("/v1/operator/incidents", headers=OPS)).json()
        if i["kind"] == "bag_balance" and i["bag_ids"] == [bag["id"]]
    )
    assert incident["expected_g"] == bag["grams"] and incident["measured_g"] == 900

    await client.post(
        f"/v1/operator/sales/{sale['id']}/confirm",
        headers=OPS,
        json={"bank_ref": "BANCO-779", "received_cop": 5_000},
    )
    waiting = await wait_line(client, sale["id"], "waiting")
    assert "incident" in waiting["lines"][0]["reason"]

    r = await client.post(
        f"/v1/operator/incidents/{incident['id']}/resolve",
        headers=OPS,
        json={"note": "Wet cardboard was mixed in; the buyer discounted it. Settle as sold."},
    )
    assert r.status_code == 200
    done = await wait_line(client, sale["id"], "settled", "failed", timeout=60)
    assert done["lines"][0]["status"] == "settled", done["lines"][0]["reason"]


async def test_an_advance_paid_by_an_earlier_treasury_is_not_paid_twice(
    app, client, settings, chain_env, bin4, collector
):
    """After the Treasury is replaced, the new one does not know the advances the old one paid.
    The settlement subtracts them from what it sends (ADR 0013, amendments)."""
    from zyrcle_api.models import Payout

    chain = chain_env["chain"]
    person = await sign_in(client, settings)
    s = await deposit(client, person, bin4, "pet", "pet_bottle", 12)  # 300 g
    await wait_state(client, person, s["id"], "verified")
    paid = await wait_payout(app, s["id"])
    async with app.state.maker() as db:  # the old Treasury had also paid 700 pesos
        row = await db.get(Payout, paid.id)
        row.amount_cop = paid.amount_cop + 700
        await db.commit()
    bag = await fill_and_seal(client, collector, bin4, "pet")
    await host_with_address(client)
    before = await balance(chain, person["address"])
    r = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={
            **sale_payload(bag),
            "ticket_ref": "T-legacy",
            "lines": [{"bag": bag["code"], "buyer_g": bag["grams"], "amount_cop": 10_000}],
        },
    )
    assert r.status_code == 201, r.text
    sale = r.json()
    await client.post(
        f"/v1/operator/sales/{sale['id']}/confirm",
        headers=OPS,
        json={"bank_ref": "BANCO-legacy", "received_cop": 10_000},
    )
    done = await wait_line(client, sale["id"], "settled", "failed")
    line = done["lines"][0]
    assert line["status"] == "settled", line["reason"]
    share = next(r for r in line["settlements"] if r["ref"] == s["id"])
    assert share["share_cop"] == 6_500  # the only deposit in the bag
    owed = 6_500 - paid.amount_cop - 700
    assert share["paid_cop"] == owed
    assert await balance(chain, person["address"]) - before == owed


async def test_the_console_suggests_the_median_price_of_a_centers_recent_sales(
    client, settings, bin4, collector
):
    center = await new_center(client)
    person = await sign_in(client, settings)
    s = await deposit(client, person, bin4, "pet", "pet_bottle", 4)
    await wait_state(client, person, s["id"], "verified")
    bag = await fill_and_seal(client, collector, bin4, "pet")
    await host_with_address(client)
    r = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={
            "buyer": center["name"],
            "center_id": center["id"],
            "ticket_ref": f"T-{uuid.uuid4().hex[:6]}",
            "sold_on": date.today().isoformat(),
            "lines": [{"bag": bag["code"], "buyer_g": bag["grams"], "amount_cop": 2_000}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["center_id"] == center["id"]
    await client.post(
        f"/v1/operator/sales/{r.json()['id']}/confirm",
        headers=OPS,
        json={"bank_ref": "BANCO-centro", "received_cop": 2_000},
    )
    await wait_line(client, r.json()["id"], "settled", "failed")
    got = await client.get(f"/v1/operator/centers/{center['id']}/suggested-prices", headers=OPS)
    assert got.json() == {"pet": {"cop_per_kg": 2_000 * 1_000 // bag["grams"], "lines": 1}}

    unknown = {**r.json(), "center_id": str(uuid.uuid4())}
    bad = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={"buyer": "x", "center_id": unknown["center_id"], "ticket_ref": "T", "lines": []},
    )
    assert bad.status_code in (404, 422)

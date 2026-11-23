"""Impact certificates (docs/adr/0027): sold material only, one claim per gram, verifiable root."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from zyrcle_api.domain.impact import (
    ANCHOR_PREFIX,
    ANCHOR_PREFIX_IPFS,
    G_CO2E_PER_KG,
    Leaf,
    anchor_data,
    co2e_g,
    merkle_root,
)
from zyrcle_api.ipfs import PinataPin, PinRejected, PinUnavailable

from .helpers import OPS, wait_for, wait_state
from .test_chain_e2e import deposit
from .test_sale import fill_and_seal, host_with_address, sale_payload, wait_line


def test_factors_follow_warm_v16():
    # (avoided MTCO2E per short ton) x 1,102.3 = grams per kilogram (ADR 0027)
    assert G_CO2E_PER_KG["pet"] == 1_168 and G_CO2E_PER_KG["metal"] == 10_086
    assert co2e_g("pet", 1_000) == 1_168
    assert co2e_g("glass", 500) == 165  # rounded down
    assert co2e_g("unknown", 1_000) == 0


def test_the_root_does_not_depend_on_order_and_changes_with_any_gram():
    leaves = [Leaf(str(uuid.uuid4()), "pet", g) for g in (100, 250, 75, 300, 10)]
    root = merkle_root(leaves)
    assert merkle_root(list(reversed(leaves))) == root
    assert merkle_root([leaves[0]]) == leaves[0].digest()
    assert merkle_root([]) == bytes(32)
    tampered = [Leaf(leaves[0].deposit_id, "pet", 101), *leaves[1:]]
    assert merkle_root(tampered) != root


def test_anchor_data_is_prefix_id_and_root():
    cid, root = uuid.uuid4(), bytes(range(32))
    data = anchor_data(cid.bytes, root)
    assert data == ANCHOR_PREFIX + cid.bytes + root
    with pytest.raises(ValueError):
        anchor_data(b"short", root)


def test_with_an_ipfs_copy_the_anchor_also_carries_its_cid():
    cid, root = uuid.uuid4(), bytes(range(32))
    ipfs = "bafkreigh2akiscaildcqabsyg3dfr6chu3fgpregiymsck7e7aqa4s52zy"
    data = anchor_data(cid.bytes, root, ipfs)
    assert data == ANCHOR_PREFIX_IPFS + cid.bytes + root + ipfs.encode()
    for bad in ("short", "bafy/../etc", "bafkrei ñ" + "a" * 20):
        with pytest.raises(ValueError):
            anchor_data(cid.bytes, root, bad)


async def test_pinata_answers_are_told_apart(pinata):
    import httpx

    async with httpx.AsyncClient() as http:
        good = PinataPin(http, pinata.url, pinata.JWT)
        cid = await good.pin_json({"a": 1}, name="t", keyvalues={})
        assert cid.startswith("bafkrei") and await good.pin_json({"a": 1}, "t", {}) == cid
        pinata.fail_next = 1
        with pytest.raises(PinUnavailable):  # try again later
            await good.pin_json({"a": 2}, "t", {})
        with pytest.raises(PinRejected):  # a wrong JWT needs a person
            await PinataPin(http, pinata.url, "wrong").pin_json({"a": 3}, "t", {})
        with pytest.raises(PinUnavailable):
            await PinataPin(http, "http://127.0.0.1:9", "x").pin_json({}, "t", {})


async def sell_one_bag(client, settings, bin4, collector, deposits: list[int]) -> list[dict]:
    """Deposits of `n` PET bottles each, one collection into one bag, one sale settled."""
    from .helpers import sign_in

    made = []
    for n in deposits:
        person = await sign_in(client, settings)
        s = await deposit(client, person, bin4, "pet", "pet_bottle", n)
        made.append(await wait_state(client, person, s["id"], "verified"))
    bag = await fill_and_seal(client, collector, bin4, "pet")
    await host_with_address(client)
    r = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={
            **sale_payload(bag),
            "ticket_ref": f"T-impact-{uuid.uuid4().hex[:6]}",
            "lines": [{"bag": bag["code"], "buyer_g": bag["grams"], "amount_cop": 5_000}],
        },
    )
    assert r.status_code == 201, r.text
    sale = r.json()
    await client.post(
        f"/v1/operator/sales/{sale['id']}/confirm",
        headers=OPS,
        json={"bank_ref": "BANCO-impact", "received_cop": 5_000},
    )
    done = await wait_line(client, sale["id"], "settled", "failed")
    assert done["lines"][0]["status"] == "settled", done["lines"][0]["reason"]
    return made


async def test_a_host_certifies_sold_material_once_and_anyone_can_verify_it(
    client, settings, chain_env, bin4, collector, pinata
):
    made = await sell_one_bag(client, settings, bin4, collector, [8, 4])
    host = next(
        h for h in (await client.get("/v1/hosts")).json() if h["name"] == "Universidad del Río"
    )
    period = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m")
    body = {"host_id": host["id"], "period": period}

    preview = (
        await client.post("/v1/operator/certificates/preview", headers=OPS, json=body)
    ).json()
    assert preview["deposits"] >= 2 and preview["factors_version"] == "warm-v16"
    assert preview["co2e_g"] == sum(m["co2e_g"] for m in preview["by_material"].values())

    r = await client.post("/v1/operator/certificates", headers=OPS, json=body)
    assert r.status_code == 201, r.text
    cert = r.json()
    assert cert["status"] == "issued" and cert["issued_by"] == "token"
    assert cert["merkle_root"] == preview["merkle_root"]

    # One gram, one claim: nothing left to certify for that month.
    r = await client.post("/v1/operator/certificates", headers=OPS, json=body)
    assert r.status_code == 409

    # The public view lists the leaves; they rebuild the same root.
    public = (await client.get(f"/v1/certificates/{cert['id']}")).json()
    leaves = [Leaf(x["deposit_id"], x["material"], x["grams"]) for x in public["leaves"]]
    assert {m["id"] for m in made} <= {x["deposit_id"] for x in public["leaves"]}
    assert "0x" + merkle_root(leaves).hex() == cert["merkle_root"]
    assert sum(x["grams"] for x in public["leaves"]) == cert["grams"]

    # The anchor worker writes the root on chain; the transaction's data says so.
    async def anchored() -> bool:
        return (await client.get(f"/v1/certificates/{cert['id']}")).json()["status"] == "anchored"

    await wait_for(anchored, timeout=15)
    done = (await client.get(f"/v1/certificates/{cert['id']}")).json()
    data = await chain_env["chain"].transaction_input(done["anchor_tx"])
    root = bytes.fromhex(cert["merkle_root"][2:])
    assert data == anchor_data(uuid.UUID(cert["id"]).bytes, root, done["ipfs_cid"])
    assert data.startswith(b"ZYRCLE-CERT-2")

    # Before anchoring, a public copy was pinned on IPFS; its CID is on chain too. The copy alone
    # rebuilds the root, and it names no operator: it is permanent.
    assert done["ipfs_url"] == settings.ipfs_gateway + done["ipfs_cid"]
    copy = pinata.pins[done["ipfs_cid"]]["pinataContent"]
    assert copy["schema"] == "zyrcle-certificate/1" and copy["id"] == cert["id"]
    assert copy["merkle"]["root"] == cert["merkle_root"]
    copied = [Leaf(x["deposit_id"], x["material"], x["grams"]) for x in copy["leaves"]]
    assert merkle_root(copied) == root
    assert copy["factors"]["g_co2e_per_kg"]["pet"] == 1_168
    assert "issued_by" not in copy and "token" not in str(copy)

    listed = (await client.get(f"/v1/hosts/{host['id']}/certificates")).json()
    assert cert["id"] in {c["id"] for c in listed}
    assert (await client.get(f"/v1/certificates/{uuid.uuid4()}")).status_code == 404


async def test_a_bad_month_or_place_is_refused(client, devices):
    host = (await client.get("/v1/hosts")).json()[0]
    r = await client.post(
        "/v1/operator/certificates/preview",
        headers=OPS,
        json={"host_id": host["id"], "period": "2026-13"},
    )
    assert r.status_code == 422
    r = await client.post(
        "/v1/operator/certificates/preview",
        headers=OPS,
        json={"host_id": str(uuid.uuid4()), "period": "2026-11"},
    )
    assert r.status_code == 404

"""Public views: platform totals, a scanned container, host and site dashboards, history."""

import pytest

from .helpers import headers
from .test_chain_e2e import deposit, wait_payout, wait_state

pytestmark = pytest.mark.integration


async def test_a_scanned_container_shows_what_it_accepts_but_never_its_code(client, devices):
    r = await client.get("/v1/containers/ctr-0002")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Contenedor ctr-0002"
    assert body["site_name"] == "Torres del Río"
    assert body["host_name"] == "Universidad del Río"
    assert body["residence_name"] == body["site_name"]  # deprecated alias for installed apps
    assert body["accepted_materials"] == ["pet", "metal", "glass"]
    assert body["online"] is True
    assert "qr" not in body and "code" not in str(body).lower()

    r = await client.get("/v1/containers/ctr-9999")
    assert r.status_code == 404


async def test_a_paid_deposit_shows_up_in_stats_dashboard_and_history(
    app, client, devices, resident
):
    before = (await client.get("/v1/stats")).json()
    site = next(s for s in (await client.get("/v1/sites")).json() if s["name"] == "Torres del Río")
    assert site["containers"] == 3
    assert site["host"]["name"] == "Universidad del Río"

    session = await deposit(client, resident, devices["ctr-0002"], "metal", "aluminum_can", 10)
    final = await wait_state(client, resident, session["id"], "verified")
    payout = await wait_payout(app, session["id"])

    after = (await client.get("/v1/stats")).json()
    assert after["deposits_verified"] == before["deposits_verified"] + 1
    assert after["kg_verified"] == pytest.approx(
        before["kg_verified"] + final["deposited_g"] / 1000, abs=0.001
    )
    assert after["paid_cop"] == before["paid_cop"] + payout.amount_cop

    dash = (await client.get(f"/v1/sites/{site['id']}/dashboard?days=7")).json()
    assert dash["site"]["name"] == "Torres del Río"
    assert dash["host"] == site["host"]
    assert len(dash["activity"]) == len(dash["payouts"]) == 7
    assert dash["activity"][-1]["kg"]["metal"] >= final["deposited_g"] / 1000
    assert dash["payouts"][-1]["cop"] >= payout.amount_cop
    ctr = next(c for c in dash["containers"] if c["id"] == "ctr-0002")
    assert ctr["online"] is True and ctr["busy"] is False
    assert ctr["kg_verified"] >= final["deposited_g"] / 1000
    assert ctr["paid_cop"] >= payout.amount_cop
    assert 0 <= ctr["fill_pct"] <= 100
    assert ctr["weight_kg"] > 0

    host = (await client.get(f"/v1/hosts/{site['host']['id']}/dashboard?days=7")).json()
    assert host["host"]["kind"] == "university"
    torres = next(s for s in host["sites"] if s["name"] == "Torres del Río")
    assert torres["totals"] == dash["totals"]
    # A host's totals add up its sites' (people are counted once, so they are not added).
    for key in ("containers", "deposits_verified", "payouts_confirmed", "paid_cop"):
        assert host["totals"][key] == sum(s["totals"][key] for s in host["sites"])
    assert len(host["activity"]) == len(host["payouts"]) == 7

    me = (await client.get("/v1/me", headers=headers(resident))).json()
    latest = me["sessions"][0]
    assert latest["id"] == session["id"]
    assert latest["container_name"] == "Contenedor ctr-0002"
    assert latest["payout"] == {
        "amount_cop": payout.amount_cop,
        "status": "confirmed",
        "tx_hash": payout.tx_hash,
    }


async def test_dashboard_rejects_bad_input(client, devices):
    site = (await client.get("/v1/sites")).json()[0]
    r = await client.get(f"/v1/sites/{site['id']}/dashboard?days=0")
    assert r.status_code == 422
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/v1/sites/{unknown}/dashboard")).status_code == 404
    assert (await client.get(f"/v1/hosts/{unknown}/dashboard")).status_code == 404


async def test_hosts_list_their_sites(client, devices):
    hosts = (await client.get("/v1/hosts")).json()
    host = next(h for h in hosts if h["name"] == "Universidad del Río")
    assert host["kind"] == "university"
    torres = next(s for s in host["sites"] if s["name"] == "Torres del Río")
    assert torres["containers"] == 3


async def test_residence_routes_remain_as_deprecated_aliases(client, devices):
    """Installed apps still call these (docs/adr/0011)."""
    old = next(
        r for r in (await client.get("/v1/residences")).json() if r["name"] == "Torres del Río"
    )
    assert old["containers"] == 3
    dash = (await client.get(f"/v1/residences/{old['id']}/dashboard?days=3")).json()
    assert dash["residence"] == dash["site"] == {"id": old["id"], "name": "Torres del Río"}


async def test_registering_a_container_answers_clearly(client, devices):
    from .helpers import OPS

    site = (await client.get("/v1/sites")).json()[0]
    body = {
        "id": "ctr-x1",
        "site_id": site["id"],
        "device_id": "no-such-device",
        "name": "X",
        "accepted_materials": ["pet"],
        "area_mm2": 250_000,
        "depth_mm": 900,
    }
    r = await client.post("/v1/operator/containers", headers=OPS, json=body)
    assert r.status_code == 404  # unknown device, not a 500
    r = await client.post(
        "/v1/operator/containers", headers=OPS, json={**body, "device_id": "ctr-0001"}
    )
    assert r.status_code == 409  # that device is already a container

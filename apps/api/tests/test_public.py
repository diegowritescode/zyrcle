"""Public views: platform totals, a scanned container, the residence dashboard, resident history."""

import pytest

from .helpers import headers
from .test_chain_e2e import deposit, wait_payout, wait_state

pytestmark = pytest.mark.integration


async def test_a_scanned_container_shows_what_it_accepts_but_never_its_code(client, devices):
    r = await client.get("/v1/containers/ctr-0002")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Contenedor ctr-0002"
    assert body["residence_name"] == "Torres del Río"
    assert body["accepted_materials"] == ["pet", "metal", "glass"]
    assert body["online"] is True
    assert "qr" not in body and "code" not in str(body).lower()

    r = await client.get("/v1/containers/ctr-9999")
    assert r.status_code == 404


async def test_a_paid_deposit_shows_up_in_stats_dashboard_and_history(
    app, client, devices, resident
):
    before = (await client.get("/v1/stats")).json()
    residence = next(
        r for r in (await client.get("/v1/residences")).json() if r["name"] == "Torres del Río"
    )
    assert residence["containers"] == 3

    session = await deposit(client, resident, devices["ctr-0002"], "metal", "aluminum_can", 10)
    final = await wait_state(client, resident, session["id"], "verified")
    payout = await wait_payout(app, session["id"])

    after = (await client.get("/v1/stats")).json()
    assert after["deposits_verified"] == before["deposits_verified"] + 1
    assert after["kg_verified"] == pytest.approx(
        before["kg_verified"] + final["deposited_g"] / 1000, abs=0.001
    )
    assert after["paid_cop"] == before["paid_cop"] + payout.amount_cop

    dash = (await client.get(f"/v1/residences/{residence['id']}/dashboard?days=7")).json()
    assert dash["residence"]["name"] == "Torres del Río"
    assert len(dash["activity"]) == len(dash["payouts"]) == 7
    assert dash["activity"][-1]["kg"]["metal"] >= final["deposited_g"] / 1000
    assert dash["payouts"][-1]["cop"] >= payout.amount_cop
    ctr = next(c for c in dash["containers"] if c["id"] == "ctr-0002")
    assert ctr["online"] is True and ctr["busy"] is False
    assert ctr["kg_verified"] >= final["deposited_g"] / 1000
    assert ctr["paid_cop"] >= payout.amount_cop
    assert 0 <= ctr["fill_pct"] <= 100
    assert ctr["weight_kg"] > 0

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
    residence = (await client.get("/v1/residences")).json()[0]
    r = await client.get(f"/v1/residences/{residence['id']}/dashboard?days=0")
    assert r.status_code == 422
    unknown = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/v1/residences/{unknown}/dashboard")).status_code == 404

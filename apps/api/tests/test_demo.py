"""Demo routes: a visitor drives a simulated container through the API."""

import pytest

from .conftest import DEMO_ORIGIN
from .helpers import headers, sign_in, wait_state

pytestmark = pytest.mark.integration


async def test_containers_list_their_live_qr(client, devices):
    listed = {c["id"]: c for c in (await client.get("/v1/demo/containers")).json()}
    assert listed["ctr-0001"]["online"] is True
    assert listed["ctr-0001"]["qr"].startswith("zyrcle://c/ctr-0001?code=")


async def test_visitor_drops_items_into_their_own_session(client, devices, resident, settings):
    container = next(
        c for c in (await client.get("/v1/demo/containers")).json() if c["id"] == "ctr-0003"
    )
    r = await client.post(
        "/v1/sessions", json={"qr": container["qr"], "material": "glass"}, headers=headers(resident)
    )
    assert r.status_code == 201, r.text
    session = r.json()
    await wait_state(client, resident, session["id"], "open")

    stranger = await sign_in(client, settings)
    r = await client.post(
        f"/v1/demo/sessions/{session['id']}/drop", json={"item": "stone"}, headers=headers(stranger)
    )
    assert r.status_code == 404  # nobody can throw stones into someone else's session

    r = await client.post(
        f"/v1/demo/sessions/{session['id']}/drop",
        json={"item": "glass_bottle", "count": 2},
        headers=headers(resident),
    )
    assert r.status_code == 200, r.text
    await wait_state(client, resident, session["id"], "depositing")
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    final = await wait_state(client, resident, session["id"], "verified")
    assert 680 <= final["deposited_g"] <= 720

    r = await client.post(
        f"/v1/demo/sessions/{session['id']}/drop",
        json={"item": "glass_bottle"},
        headers=headers(resident),
    )
    assert r.status_code == 409  # lid closed


async def test_demo_page_origin_is_allowed_by_cors(client):
    r = await client.options(
        "/v1/demo/containers",
        headers={"Origin": DEMO_ORIGIN, "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == DEMO_ORIGIN
    r = await client.options(
        "/v1/demo/containers",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in r.headers

"""End-to-end: real API, real Postgres, real Mosquitto (with ACL), simulated containers.

Run `dev/mosquitto/make-passwd.sh && docker compose -f dev/compose.yml up -d` first.
"""

import json

import aiomqtt
import pytest
from sqlalchemy import func, select
from zyrcle_protocol import Envelope, generate_private_key, seal, up_topic

from zyrcle_api.models import DeviceMessage

from .helpers import OPS, headers, qr, sign_in, wait_for, wait_state

pytestmark = pytest.mark.integration


async def start(client, resident, runner, material="pet"):
    r = await client.post(
        "/v1/sessions", json={"qr": qr(runner), "material": material}, headers=headers(resident)
    )
    assert r.status_code == 201, r.text
    session = r.json()
    await wait_state(client, resident, session["id"], "open")
    return session


async def test_pet_bottles_are_verified(client, devices, resident):
    runner = devices["ctr-0001"]
    session = await start(client, resident, runner)
    runner.c.deposit("pet_bottle", 3)
    await wait_state(client, resident, session["id"], "depositing")
    r = await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    assert r.status_code == 200, r.text
    final = await wait_state(client, resident, session["id"], "verified")
    assert 65 <= final["deposited_g"] <= 85
    assert final["close_reason"] == "resident_finished" and final["reasons"] == []


async def test_stone_goes_to_review_and_operator_rejects(client, devices, resident):
    runner = devices["ctr-0002"]
    session = await start(client, resident, runner)
    runner.c.deposit("stone")
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    final = await wait_state(client, resident, session["id"], "review")
    assert final["score"] == 0.0 and any("too dense" in r for r in final["reasons"])

    queue = (await client.get("/v1/operator/review", headers=OPS)).json()
    assert session["id"] in [s["id"] for s in queue]
    r = await client.post(
        f"/v1/operator/sessions/{session['id']}/review",
        headers=OPS,
        json={"approve": False, "note": "piedra"},
    )
    assert r.json()["state"] == "rejected"


async def test_walking_away_still_credits_the_deposit(client, devices, resident):
    runner = devices["ctr-0003"]
    session = await start(client, resident, runner, material="metal")
    runner.c.deposit("aluminum_can", 4)
    final = await wait_state(client, resident, session["id"], "verified", timeout=10)
    assert final["close_reason"] == "idle" and 50 <= final["deposited_g"] <= 70


async def test_opening_without_depositing_is_empty(client, devices, resident):
    runner = devices["ctr-0001"]
    session = await start(client, resident, runner)
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    final = await wait_state(client, resident, session["id"], "empty")
    assert final["deposited_g"] == 0


async def test_busy_container_rejects_a_second_resident(client, devices, resident, settings):
    runner = devices["ctr-0002"]
    session = await start(client, resident, runner)
    other = await sign_in(client, settings)
    r = await client.post(
        "/v1/sessions", json={"qr": qr(runner), "material": "pet"}, headers=headers(other)
    )
    assert r.status_code == 409 and "busy" in r.json()["detail"]["detail"]
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    await wait_state(client, resident, session["id"], "empty")


async def test_stale_or_forged_codes_are_refused(client, devices, resident):
    runner = devices["ctr-0003"]
    r = await client.post(
        "/v1/sessions",
        json={"qr": "zyrcle://c/ctr-0003?code=ZZZZZZ", "material": "pet"},
        headers=headers(resident),
    )
    assert r.status_code == 403
    r = await client.post(
        "/v1/sessions", json={"qr": qr(runner), "material": "paper"}, headers=headers(resident)
    )
    assert r.status_code == 422  # this container does not take paper


async def test_replayed_and_forged_messages_have_no_effect(app, client, devices, settings):
    runner = devices["ctr-0001"]
    service = app.state.sessions

    async def stored() -> int:
        async with app.state.maker() as db:
            return await db.scalar(
                select(func.count())
                .select_from(DeviceMessage)
                .where(DeviceMessage.device_id == "ctr-0001")
            )

    replay = runner.sent[-1]
    forged = seal(
        generate_private_key(), Envelope("ctr-0001", 2**62, 0, "event", {"name": "lock_opened"})
    )
    rejected_before = service.rejected_messages
    before = await stored()
    async with aiomqtt.Client(
        settings.mqtt_host, username="ctr-0001", password="dev-password"
    ) as attacker:
        await attacker.publish(up_topic("ctr-0001", json.loads(replay)["type"]), replay, qos=1)
        await attacker.publish(up_topic("ctr-0001", "event"), forged, qos=1)
    await wait_for(lambda: service.rejected_messages == rejected_before + 1)
    assert await stored() == before  # the replay was a no-op, the forgery never got stored


async def test_broker_acl_stops_a_device_impersonating_another(app, client, devices, settings):
    service = app.state.sessions
    rejected_before = service.rejected_messages
    async with aiomqtt.Client(
        settings.mqtt_host, username="ctr-0002", password="dev-password"
    ) as intruder:
        await intruder.publish(up_topic("ctr-0001", "hello"), b"{}", qos=1)
    await __import__("asyncio").sleep(0.5)
    # The broker dropped it: the API never even saw a message to reject.
    assert service.rejected_messages == rejected_before


async def test_siwe_nonce_cannot_be_reused(client, settings):
    from datetime import UTC, datetime

    from eth_account import Account
    from eth_account.messages import encode_defunct

    from zyrcle_api.auth import build_siwe

    account = Account.create()
    nonce = (await client.post("/v1/auth/nonce")).json()["nonce"]
    message = build_siwe(
        settings.siwe_domain, account.address, settings.chain_id, nonce, datetime.now(UTC)
    )
    body = {
        "message": message,
        "signature": account.sign_message(encode_defunct(text=message)).signature.hex(),
    }
    assert (await client.post("/v1/auth/verify", json=body)).status_code == 200
    assert (await client.post("/v1/auth/verify", json=body)).status_code == 401
    wrong_domain = message.replace(settings.siwe_domain, "evil.example", 1)
    body = {
        "message": wrong_domain,
        "signature": account.sign_message(encode_defunct(text=wrong_domain)).signature.hex(),
    }
    assert (await client.post("/v1/auth/verify", json=body)).status_code == 401


async def test_live_websocket_streams_readings_and_states(
    client, devices, resident, server_url, settings, monkeypatch
):
    import websockets

    # The suite's 2 s idle timeout can close the lid before a slow CI runner delivers the first
    # heavier reading (states: closing, verified; no depositing). This test is about streaming.
    monkeypatch.setattr(settings, "idle_timeout_s", 30)
    runner = devices["ctr-0001"]
    session = await start(client, resident, runner)
    token = resident["Authorization"].removeprefix("Bearer ")
    url = f"ws://{server_url}/v1/sessions/{session['id']}/live?token={token}"
    events: list[dict] = []
    async with websockets.connect(url) as ws:
        first = json.loads(await ws.recv())
        assert first["type"] == "state" and first["state"] == "open"
        runner.c.deposit("pet_bottle", 2)
        async for raw in ws:  # wait until the server sees the weight go up
            event = json.loads(raw)
            events.append(event)
            if event["type"] == "state" and event["state"] == "depositing":
                break
        await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
        async for raw in ws:  # the server closes the socket once the session is final
            events.append(json.loads(raw))
    states = [e["state"] for e in events if e["type"] == "state"]
    assert states[-1] == "verified" and "depositing" in states and "closing" in states
    assert any(e["type"] == "reading" for e in events)


async def test_live_websocket_keeps_a_change_made_while_it_connects(
    app, client, devices, resident, server_url, monkeypatch
):
    """A change committed while the socket is being set up must still reach the page: CI caught
    the page stuck on "Abriendo la tapa…" because the lid opened between the server's read and its
    subscription. Here every read races a change, published the instant after it returns."""
    import asyncio

    import websockets

    from zyrcle_api.sessions import session_view

    runner = devices["ctr-0002"]
    session = await start(client, resident, runner)
    read = app.state.sessions.get

    async def read_then_change(session_id):
        s = await read(session_id)
        event = {"type": "state", **session_view(s), "state": "depositing"}
        app.state.hub.publish(str(session_id), event)
        return s

    monkeypatch.setattr(app.state.sessions, "get", read_then_change)
    token = resident["Authorization"].removeprefix("Bearer ")
    url = f"ws://{server_url}/v1/sessions/{session['id']}/live?token={token}"
    async with websockets.connect(url) as ws:
        assert json.loads(await ws.recv())["state"] == "open"  # the read
        async with asyncio.timeout(5):  # the change that raced it, not lost
            while (event := json.loads(await ws.recv()))["type"] != "state":
                pass
        assert event["state"] == "depositing"
    monkeypatch.undo()
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    await wait_state(client, resident, session["id"], "empty", "verified")


async def test_websocket_rejects_other_residents(client, devices, resident, settings, server_url):
    import websockets

    runner = devices["ctr-0002"]
    session = await start(client, resident, runner)
    other = await sign_in(client, settings)
    token = other["Authorization"].removeprefix("Bearer ")
    # The handshake itself is refused: another resident's token never gets a socket.
    with pytest.raises(websockets.InvalidStatus) as refused:
        await websockets.connect(
            f"ws://{server_url}/v1/sessions/{session['id']}/live?token={token}"
        )
    assert refused.value.response.status_code == 403
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    await wait_state(client, resident, session["id"], "empty")


async def test_nobody_learns_whether_someone_elses_session_exists(
    client, devices, resident, settings
):
    from .helpers import sign_in

    stranger = await sign_in(client, settings)
    session = await deposit_start(client, resident, devices["ctr-0001"])
    r = await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(stranger))
    assert r.status_code == 404
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    await wait_state(client, resident, session["id"], "empty", "verified")


async def deposit_start(client, resident, runner) -> dict:
    r = await client.post(
        "/v1/sessions", json={"qr": qr(runner), "material": "pet"}, headers=headers(resident)
    )
    assert r.status_code == 201, r.text
    await wait_state(client, resident, r.json()["id"], "open")
    return r.json()

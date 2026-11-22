"""Push notifications: registration, what gets pushed, and how failures are handled."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update

from zyrcle_api.models import Notification, PushToken
from zyrcle_api.notifications import enqueue

from .helpers import OPS, headers, qr, sign_in, wait_for, wait_state
from .test_chain_e2e import deposit, wait_payout

pytestmark = pytest.mark.integration


def _token(label: str) -> str:
    return f"ExponentPushToken[{label}-{uuid.uuid4().hex[:12]}]"


async def _register(client, resident, token: str, platform: str = "android") -> None:
    r = await client.put(
        "/v1/me/push-token", json={"token": token, "platform": platform}, headers=headers(resident)
    )
    assert r.status_code == 204, r.text


async def _push(app, resident, key: str) -> uuid.UUID:
    """Queue a notification directly, as a payout or a review would."""
    async with app.state.maker() as db:
        await enqueue(
            db,
            resident_id=uuid.UUID(resident["id"]),
            kind="payout_confirmed",
            dedupe_key=key,
            title="Te pagamos $10",
            body="Prueba",
            data={"url": "/history"},
            now=datetime.now(UTC),
        )
        await db.commit()
        return await db.scalar(select(Notification.id).where(Notification.dedupe_key == key))


async def _notification(app, notification_id) -> Notification:
    async with app.state.maker() as db:
        return await db.get(Notification, notification_id)


async def _token_row(app, token: str) -> PushToken:
    async with app.state.maker() as db:
        return await db.get(PushToken, token)


async def test_a_paid_deposit_reaches_the_residents_phone(app, client, devices, resident, expo):
    bad = await client.put(
        "/v1/me/push-token",
        json={"token": "not-a-token", "platform": "android"},
        headers=headers(resident),
    )
    assert bad.status_code == 422
    token = _token("phone")
    await _register(client, resident, token)

    session = await deposit(client, resident, devices["ctr-0002"], "metal", "aluminum_can", 6)
    await wait_state(client, resident, session["id"], "verified")
    payout = await wait_payout(app, session["id"])
    await wait_for(lambda: expo.to(token), timeout=5)

    [message] = expo.to(token)
    assert message["title"] == f"Te pagamos ${payout.amount_cop}"
    assert "latas en Contenedor ctr-0002" in message["body"]
    assert message["channelId"] == "payments" and message["sound"] == "default"
    assert message["data"]["url"] == "/history"
    assert message["data"]["session_id"] == session["id"]
    assert message["data"]["kind"] == "payout_confirmed"


async def test_review_and_its_verdict_are_pushed(client, devices, resident, expo):
    token = _token("review")
    await _register(client, resident, token, "ios")
    runner = devices["ctr-0002"]
    r = await client.post(
        "/v1/sessions", json={"qr": qr(runner), "material": "metal"}, headers=headers(resident)
    )
    session = r.json()
    await wait_state(client, resident, session["id"], "open")
    runner.c.deposit("stone")
    await client.post(f"/v1/sessions/{session['id']}/finish", headers=headers(resident))
    await wait_state(client, resident, session["id"], "review")
    await wait_for(lambda: expo.to(token), timeout=5)
    assert expo.to(token)[0]["title"] == "Tu depósito quedó en revisión"

    await client.post(
        f"/v1/operator/sessions/{session['id']}/review",
        headers=OPS,
        json={"approve": False, "note": "piedra"},
    )
    await wait_for(lambda: len(expo.to(token)) == 2, timeout=5)
    verdict = expo.to(token)[1]
    assert verdict["title"] == "Tu depósito no fue aprobado"
    assert verdict["body"].endswith("Motivo: piedra")
    assert verdict["channelId"] == "deposits"


async def test_a_token_follows_the_wallet_now_on_the_phone(app, client, devices, settings, expo):
    old, new = await sign_in(client, settings), await sign_in(client, settings)
    token = _token("shared")
    await _register(client, old, token)
    await _register(client, new, token)
    assert str((await _token_row(app, token)).resident_id) == new["id"]

    skipped = await _push(app, old, f"test:{uuid.uuid4()}")
    await wait_for(lambda: _status(app, skipped, "skipped"), timeout=5)
    assert expo.to(token) == []

    key = f"test:{uuid.uuid4()}"
    first = await _push(app, new, key)
    assert await _push(app, new, key) == first  # same key: queued once
    async with app.state.maker() as db:
        count = await db.scalar(select(func.count()).where(Notification.dedupe_key == key))
    assert count == 1
    await wait_for(lambda: len(expo.to(token)) == 1, timeout=5)


async def _status(app, notification_id, status: str) -> bool:
    return (await _notification(app, notification_id)).status == status


async def test_uninstalled_apps_stop_receiving(app, client, devices, settings, expo):
    # Rejected at send time.
    a = await sign_in(client, settings)
    gone = _token("gone")
    await _register(client, a, gone)
    failed = await _push(app, a, f"test:{uuid.uuid4()}")
    await wait_for(lambda: _status(app, failed, "failed"), timeout=5)
    assert (await _token_row(app, gone)).disabled_at is not None
    assert "DeviceNotRegistered" in (await _notification(app, failed)).last_error

    # Accepted by Expo, then reported in the receipt (checked after push_receipt_delay_s).
    b = await sign_in(client, settings)
    uninstalled = _token("uninstalled")
    await _register(client, b, uninstalled)
    sent = await _push(app, b, f"test:{uuid.uuid4()}")
    await wait_for(lambda: _status(app, sent, "sent"), timeout=5)

    async def disabled() -> bool:
        return (await _token_row(app, uninstalled)).disabled_at is not None

    await wait_for(disabled, timeout=8)
    assert (await _notification(app, sent)).receipts_checked_at is not None

    # Registering again (the app was reinstalled) turns the token back on.
    await _register(client, b, uninstalled)
    assert (await _token_row(app, uninstalled)).disabled_at is None


async def test_expo_outages_are_retried(app, client, devices, settings, expo):
    resident = await sign_in(client, settings)
    token = _token("retry")
    await _register(client, resident, token)
    expo.fail_next = 1
    queued = await _push(app, resident, f"test:{uuid.uuid4()}")

    async def retried() -> bool:
        n = await _notification(app, queued)
        return n.attempts == 1 and n.status == "pending" and n.next_attempt_at is not None

    await wait_for(retried, timeout=5)
    assert "503" in (await _notification(app, queued)).last_error
    async with app.state.maker() as db:  # skip the backoff
        await db.execute(
            update(Notification)
            .where(Notification.id == queued)
            .values(next_attempt_at=datetime.now(UTC))
        )
        await db.commit()
    await wait_for(lambda: _status(app, queued, "sent"), timeout=5)
    assert len(expo.to(token)) == 1

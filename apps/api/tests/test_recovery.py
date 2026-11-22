"""Recovery email and lost-phone recovery: API, workers, Resend (fake) and accounts on anvil
(docs/adr/0010-smart-accounts-and-recovery.md)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from eth_account import Account
from sqlalchemy import select, update

from zyrcle_api.chain import WEI_PER_COP, account_address
from zyrcle_api.models import AccountRecovery, EmailCode, EmailMessage, PushToken, Resident

from .helpers import headers, sign_in, siwe, wait_for

pytestmark = pytest.mark.integration


def new_email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:8]}@example.com"


async def wait_email(resend, address: str, count: int) -> dict:
    await wait_for(lambda: len(resend.to(address)) >= count, timeout=5)
    return resend.to(address)[count - 1]


async def confirm_email(client, resend, resident, email: str) -> None:
    before = len(resend.to(email))
    r = await client.post("/v1/me/email", json={"email": email}, headers=headers(resident))
    assert r.status_code == 202, r.text
    await wait_email(resend, email, before + 1)
    r = await client.post(
        "/v1/me/email/verify",
        json={"email": email, "code": resend.last_code(email)},
        headers=headers(resident),
    )
    assert r.status_code == 200, r.text


async def account(client, resident) -> dict:
    r = await client.get("/v1/me/account", headers=headers(resident))
    assert r.status_code == 200, r.text
    return r.json()


async def push_token(client, resident, name: str) -> str:
    token = f"ExponentPushToken[{name}-{uuid.uuid4().hex[:8]}]"
    r = await client.put(
        "/v1/me/push-token",
        json={"token": token, "platform": "android"},
        headers=headers(resident),
    )
    assert r.status_code == 204, r.text
    return token


async def ask_recovery(client, resend, phone, email: str) -> dict:
    before = len(resend.to(email))
    r = await client.post("/v1/recovery/code", json={"email": email}, headers=headers(phone))
    assert r.status_code == 202, r.text
    await wait_email(resend, email, before + 1)
    r = await client.post(
        "/v1/recovery",
        json={"email": email, "code": resend.last_code(email)},
        headers=headers(phone),
    )
    assert r.status_code == 201, r.text
    return r.json()


async def recovery_row(app, recovery_id: str) -> AccountRecovery:
    async with app.state.maker() as db:
        row = await db.get(AccountRecovery, uuid.UUID(recovery_id))
        assert row is not None
        return row


async def wait_recovery(app, recovery_id: str, status: str) -> AccountRecovery:
    holder = {}

    async def reached() -> bool:
        holder["r"] = await recovery_row(app, recovery_id)
        return holder["r"].status == status

    await wait_for(reached, timeout=15)
    return holder["r"]


async def test_a_resident_confirms_a_recovery_email(app, client, settings, resend):
    ana = await sign_in(client, settings)
    before = await account(client, ana)
    assert before["email"] is None and before["recovery_available"] and before["can_recover"]

    email = new_email("ana")
    typed = f"  {email.upper()} "  # people type spaces and capitals
    r = await client.post("/v1/me/email", json={"email": typed}, headers=headers(ana))
    assert r.status_code == 202, r.text
    assert r.json()["sent_to"] == f"a•••@{email.split('@')[1]}"
    mail = await wait_email(resend, email, 1)
    code = resend.last_code(email)
    assert code in mail["subject"] and "Zyrcle" in mail["from"]

    wrong = "000000" if code != "000000" else "111111"
    r = await client.post(
        "/v1/me/email/verify", json={"email": email, "code": wrong}, headers=headers(ana)
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "code_invalid"
    r = await client.post(
        "/v1/me/email/verify", json={"email": typed, "code": code}, headers=headers(ana)
    )
    assert r.status_code == 200, r.text
    after = await account(client, ana)
    assert after["email"] == email and after["email_verified_at"]
    assert not after["can_recover"]  # a phone with its own email is an account, not a new phone

    # The code does not stay readable in the outbox once sent.
    async with app.state.maker() as db:
        row = await db.scalar(select(EmailMessage).where(EmailMessage.to == email))
        assert row.status == "sent" and row.text_body == "" and code not in row.subject

    beto = await sign_in(client, settings)
    r = await client.post("/v1/me/email", json={"email": email}, headers=headers(beto))
    assert r.status_code == 429  # one code a minute per address
    async with app.state.maker() as db:
        await db.execute(
            update(EmailCode)
            .where(EmailCode.email == email)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=2))
        )
        await db.commit()
    await confirm_email_expecting(client, resend, beto, email, status=409, code="email_taken")


async def confirm_email_expecting(client, resend, resident, email, status, code):
    before = len(resend.to(email))
    r = await client.post("/v1/me/email", json={"email": email}, headers=headers(resident))
    assert r.status_code == 202, r.text
    await wait_email(resend, email, before + 1)
    r = await client.post(
        "/v1/me/email/verify",
        json={"email": email, "code": resend.last_code(email)},
        headers=headers(resident),
    )
    assert r.status_code == status and r.json()["detail"]["code"] == code, r.text


async def test_a_code_dies_after_five_wrong_guesses_or_ten_minutes(app, client, settings, resend):
    carla = await sign_in(client, settings)
    email = new_email("carla")
    r = await client.post("/v1/me/email", json={"email": email}, headers=headers(carla))
    assert r.status_code == 202
    await wait_email(resend, email, 1)
    code = resend.last_code(email)
    wrong = "000000" if code != "000000" else "111111"
    for left in (4, 3, 2, 1, 0):
        r = await client.post(
            "/v1/me/email/verify", json={"email": email, "code": wrong}, headers=headers(carla)
        )
        assert r.status_code == 422 and f"{left} attempts left" in r.json()["detail"]["detail"]
    r = await client.post(
        "/v1/me/email/verify", json={"email": email, "code": code}, headers=headers(carla)
    )
    assert r.status_code == 422, "a burnt code stays burnt"

    async with app.state.maker() as db:
        await db.execute(
            update(EmailCode)
            .where(EmailCode.email == email)
            .values(created_at=datetime.now(UTC) - timedelta(minutes=2))
        )
        await db.commit()
    r = await client.post("/v1/me/email", json={"email": email}, headers=headers(carla))
    assert r.status_code == 202
    await wait_email(resend, email, 2)
    async with app.state.maker() as db:
        await db.execute(
            update(EmailCode)
            .where(EmailCode.email == email, EmailCode.used_at.is_(None))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
    r = await client.post(
        "/v1/me/email/verify",
        json={"email": email, "code": resend.last_code(email)},
        headers=headers(carla),
    )
    assert r.status_code == 422, "an expired code is refused"


async def test_a_lost_phone_gets_its_account_back_after_the_wait(
    app, client, settings, resend, expo, chain_env
):
    chain = chain_env["chain"]
    old = await sign_in(client, settings)
    email = new_email("diana")
    await confirm_email(client, resend, old, email)
    old_token = await push_token(client, old, "old-phone")
    balance = 7_250 * WEI_PER_COP
    await chain.w3.provider.make_request("anvil_setBalance", [old["address"], hex(balance)])

    new = await sign_in(client, settings)
    assert (await account(client, new))["can_recover"]
    new_token = await push_token(client, new, "new-phone")
    started = await ask_recovery(client, resend, new, email)
    assert started["status"] == "starting"

    waiting = await wait_recovery(app, started["id"], "waiting")
    assert await chain.is_deployed(old["address"])
    pending = await chain.pending_recovery(old["address"])
    assert pending.new_owner == new["key"].address.lower()
    assert waiting.ready_at == datetime.fromtimestamp(pending.ready_at, UTC)

    # The phone that has the account hears about it, by push and by email.
    await wait_for(lambda: expo.to(old_token), timeout=5)
    alert = expo.to(old_token)[-1]
    assert alert["data"]["kind"] == "recovery_started" and alert["channelId"] == "account"
    assert "pasará a otro teléfono" in (await wait_email(resend, email, 3))["subject"]
    assert (await account(client, old))["incoming"]["status"] == "waiting"
    mine = await account(client, new)
    assert mine["outgoing"]["status"] == "waiting" and not mine["can_recover"]

    # Meanwhile the new phone cannot earn or book into the wrong account.
    r = await client.post(
        "/v1/bookings",
        json={"container_id": "ctr-0001", "starts_at": "2030-01-01T10:00:00-05:00"},
        headers=headers(new),
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "recovery_pending"

    await chain.w3.provider.make_request("evm_increaseTime", [48 * 3600 + 60])
    await chain.w3.provider.make_request("evm_mine", [])
    async with app.state.maker() as db:
        await db.execute(
            update(AccountRecovery)
            .where(AccountRecovery.id == uuid.UUID(started["id"]))
            .values(next_attempt_at=datetime.now(UTC))
        )
        await db.commit()
    done = await wait_recovery(app, started["id"], "done")
    assert done.finish_tx
    assert await chain.account_owner(old["address"]) == new["key"].address.lower()
    assert await chain.balance_wei(old["address"]) == balance

    # Both old sessions end: the old phone's key lost the account, the new phone's resident is gone.
    assert (await client.get("/v1/me/account", headers=headers(old))).status_code == 401
    assert (await client.get("/v1/me/account", headers=headers(new))).status_code == 401

    again = await sign_in(client, settings, new["key"])
    assert again["id"] == old["id"] and again["address"] == old["address"]
    view = await account(client, again)
    assert view["email"] == email and view["recovered_at"] and view["incoming"] is None
    async with app.state.maker() as db:
        tokens = {t.token: t.resident_id for t in await db.scalars(select(PushToken))}
        assert old_token not in tokens
        assert tokens[new_token] == uuid.UUID(old["id"])
        assert await db.get(Resident, uuid.UUID(new["id"])) is None
    await wait_for(
        lambda: any(m["data"]["kind"] == "recovery_done" for m in expo.to(new_token)), timeout=5
    )
    assert "ya está en tu teléfono nuevo" in (await wait_email(resend, email, 4))["subject"]

    # The lost phone, if it turns up, cannot sign back in.
    r = await siwe(client, settings, old["key"])
    assert r.status_code == 403 and r.json()["detail"]["code"] == "key_retired"


async def test_the_owner_cancels_a_recovery_it_did_not_ask_for(
    app, client, settings, resend, expo, chain_env
):
    chain = chain_env["chain"]
    owner = await sign_in(client, settings)
    email = new_email("elena")
    await confirm_email(client, resend, owner, email)
    thief = await sign_in(client, settings)
    thief_token = await push_token(client, thief, "thief")
    started = await ask_recovery(client, resend, thief, email)
    await wait_recovery(app, started["id"], "waiting")

    r = await client.delete(f"/v1/recovery/{started['id']}", headers=headers(owner))
    assert r.status_code == 200 and r.json()["status"] == "cancelling"
    cancelled = await wait_recovery(app, started["id"], "cancelled")
    assert cancelled.cancelled_by == "owner" and cancelled.cancel_tx
    assert (await chain.pending_recovery(owner["address"])).new_owner is None
    assert await chain.account_owner(owner["address"]) == owner["key"].address.lower()

    await wait_for(
        lambda: any(m["data"]["kind"] == "recovery_cancelled" for m in expo.to(thief_token)),
        timeout=5,
    )
    assert "Se canceló" in (await wait_email(resend, email, 4))["subject"]
    assert (await account(client, thief))["outgoing"]["status"] == "cancelled"
    assert (await account(client, owner))["incoming"] is None

    stranger = await sign_in(client, settings)
    r = await client.delete(f"/v1/recovery/{started['id']}", headers=headers(stranger))
    assert r.status_code == 404


async def test_asking_for_a_code_does_not_reveal_whether_an_email_has_an_account(
    client, settings, resend
):
    phone = await sign_in(client, settings)
    nobody = new_email("nadie")
    r = await client.post("/v1/recovery/code", json={"email": nobody}, headers=headers(phone))
    assert r.status_code == 202
    assert r.json()["sent_to"].endswith("@example.com")
    r = await client.post(
        "/v1/recovery", json={"email": nobody, "code": "123456"}, headers=headers(phone)
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "code_invalid"
    assert resend.to(nobody) == []
    r = await client.post(
        "/v1/recovery/code", json={"email": "no-es-un-correo"}, headers=headers(phone)
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_email"


async def test_a_phone_with_its_own_history_cannot_take_over_an_account(client, settings, resend):
    owner = await sign_in(client, settings)
    email = new_email("fabio")
    await confirm_email(client, resend, owner, email)
    busy = await sign_in(client, settings)
    await confirm_email(client, resend, busy, new_email("busy"))

    before = len(resend.to(email))
    r = await client.post("/v1/recovery/code", json={"email": email}, headers=headers(busy))
    assert r.status_code == 202
    await wait_email(resend, email, before + 1)
    r = await client.post(
        "/v1/recovery",
        json={"email": email, "code": resend.last_code(email)},
        headers=headers(busy),
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "phone_in_use"


async def test_residents_from_before_smart_accounts_get_one_when_they_sign_in(
    app, client, settings, chain_env
):
    key = Account.create()
    legacy = key.address.lower()
    async with app.state.maker() as db:
        db.add(Resident(id=uuid.uuid4(), address=legacy, owner_address=legacy))
        await db.commit()
    resident = await sign_in(client, settings, key)
    expected = account_address(chain_env["factory"], legacy)
    assert resident["address"] == expected
    assert expected == await chain_env["chain"].predict_account(legacy)
    assert expected != legacy

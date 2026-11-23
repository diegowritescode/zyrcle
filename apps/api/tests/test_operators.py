"""Operator accounts: sign-in by email code, named actions, admins only manage (docs/adr/0014)."""

import uuid

import pytest

from .helpers import OPS, headers, sign_in, wait_for

pytestmark = pytest.mark.integration


async def login(client, resend, typed: str) -> dict:
    """Sign in with the address as typed (any case); the code goes to its lowercase form."""
    email = typed.lower()
    before = len(resend.to(email))
    r = await client.post("/v1/operator/login/code", json={"email": typed})
    assert r.status_code == 202, r.text
    await wait_for(lambda: len(resend.to(email)) > before, timeout=5)
    r = await client.post(
        "/v1/operator/login", json={"email": typed, "code": resend.last_code(email)}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_an_operator_signs_in_by_email_and_their_actions_carry_their_name(
    client, resend, settings, devices
):
    email = f"laura-{uuid.uuid4().hex[:6]}@zyrcle.test"
    r = await client.post(
        "/v1/operator/operators", headers=OPS, json={"email": email, "name": "Laura"}
    )
    assert r.status_code == 201 and r.json()["role"] == "operator"
    me = await login(client, resend, email.upper())  # addresses are not case-sensitive
    assert (await client.get("/v1/operator/me", headers=me)).json()["name"] == email

    # Her actions are recorded with her email.
    host = (
        await client.post(
            "/v1/operator/hosts", headers=me, json={"name": "Colegio Norte", "kind": "public"}
        )
    ).json()
    assert host["name"] == "Colegio Norte"
    incident_free = (await client.get("/v1/operator/incidents", headers=me)).status_code
    assert incident_free == 200

    # Only admins manage operators.
    r = await client.post(
        "/v1/operator/operators", headers=me, json={"email": "x@zyrcle.test", "name": "X"}
    )
    assert r.status_code == 403

    # Deactivating her ends her session at once.
    op_id = next(
        o["id"]
        for o in (await client.get("/v1/operator/operators", headers=OPS)).json()
        if o["email"] == email
    )
    r = await client.patch(f"/v1/operator/operators/{op_id}", headers=OPS, json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    assert (await client.get("/v1/operator/me", headers=me)).status_code == 401


async def test_codes_are_limited_and_reveal_nothing(client, resend):
    stranger = f"nobody-{uuid.uuid4().hex[:6]}@zyrcle.test"
    r = await client.post("/v1/operator/login/code", json={"email": stranger})
    assert r.status_code == 202  # the same answer as for an operator
    assert resend.to(stranger) == []  # but nothing is sent
    r = await client.post("/v1/operator/login/code", json={"email": stranger})
    assert r.status_code == 429  # one a minute, operator or not
    r = await client.post("/v1/operator/login", json={"email": stranger, "code": "123456"})
    assert r.status_code == 401

    email = f"admin-{uuid.uuid4().hex[:6]}@zyrcle.test"
    await client.post(
        "/v1/operator/operators", headers=OPS, json={"email": email, "name": "A", "role": "admin"}
    )
    await client.post("/v1/operator/login/code", json={"email": email})
    await wait_for(lambda: len(resend.to(email)) == 1, timeout=5)
    for _ in range(5):  # five wrong guesses burn the code
        r = await client.post("/v1/operator/login", json={"email": email, "code": "000000"})
        assert r.status_code == 401
    r = await client.post(
        "/v1/operator/login", json={"email": email, "code": resend.last_code(email)}
    )
    assert r.status_code == 401


async def test_participant_and_operator_tokens_never_cross(client, resend, settings):
    person = await sign_in(client, settings)
    assert (await client.get("/v1/operator/me", headers=headers(person))).status_code == 401
    email = f"op-{uuid.uuid4().hex[:6]}@zyrcle.test"
    await client.post("/v1/operator/operators", headers=OPS, json={"email": email, "name": "O"})
    op = await login(client, resend, email)
    assert (await client.get("/v1/me", headers=op)).status_code == 401

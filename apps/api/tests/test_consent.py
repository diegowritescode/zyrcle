"""Consent to the data-processing policy, Ley 1581 de 2012 (docs/adr/0028)."""

import pytest

from .helpers import headers, qr, sign_in

pytestmark = pytest.mark.integration


async def test_a_participant_accepts_the_policy_in_force(client, settings):
    person = await sign_in(client, settings)
    me = (await client.get("/v1/me", headers=headers(person))).json()
    assert me["privacy_version"] is None and me["privacy_current"] == settings.privacy_version
    r = await client.post("/v1/me/consent", headers=headers(person), json={"version": "1999-01-01"})
    assert r.status_code == 409  # not the policy in force
    r = await client.post(
        "/v1/me/consent", headers=headers(person), json={"version": settings.privacy_version}
    )
    assert r.status_code == 200
    me = (await client.get("/v1/me", headers=headers(person))).json()
    assert me["privacy_version"] == settings.privacy_version


async def test_when_required_nobody_deposits_without_consent(client, settings, devices):
    person = await sign_in(client, settings)
    settings.require_consent = True
    try:
        r = await client.post(
            "/v1/sessions",
            headers=headers(person),
            json={"qr": qr(devices["ctr-0002"]), "material": "metal"},
        )
        assert r.status_code == 403 and r.json()["detail"]["code"] == "consent_required"
    finally:
        settings.require_consent = False

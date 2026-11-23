"""Health report and admin alerts (docs/adr/0028)."""

import uuid

import pytest
from sqlalchemy import select

from zyrcle_api.health import AlertWorker, report
from zyrcle_api.main import create_app
from zyrcle_api.models import EmailMessage

from .helpers import OPS

pytestmark = pytest.mark.integration


async def test_operators_see_outboxes_chain_and_gas(client, devices):
    r = await client.get("/v1/operator/health", headers=OPS)
    assert r.status_code == 200, r.text
    h = r.json()
    names = {b["name"] for b in h["outboxes"]}
    assert {"anticipos", "avisos push", "correos", "liquidaciones", "certificados"} <= names
    assert h["mqtt"] is True and h["devices"]["online"] >= 3
    assert h["chain"]["block"] >= 1 and h["chain"]["available_cop"] > 0
    assert set(h["chain"]["keys"]) == {"oráculo", "operador"}
    assert (await client.get("/v1/operator/health")).status_code == 401


async def test_low_gas_is_emailed_to_admins_once_a_day(app, client, settings):
    email = f"admin-{uuid.uuid4().hex[:6]}@zyrcle.test"
    await client.post(
        "/v1/operator/operators", headers=OPS, json={"email": email, "name": "A", "role": "admin"}
    )
    strict = settings.model_copy(update={"alert_gas_min_zyr": 10**12})  # every key is "low"
    keys = {"oráculo": "0x" + "1" * 40}

    async def snapshot():
        return await report(app.state.maker, strict, app.state.chain, keys, True)

    current = await snapshot()
    assert not current["ok"] and any(w["kind"] == "gas:oráculo" for w in current["warnings"])
    worker = AlertWorker(app.state.maker, strict, snapshot)
    await worker.run_once()
    await worker.run_once()  # the same day: no second email
    async with app.state.maker() as db:
        sent = list(
            await db.scalars(
                select(EmailMessage).where(EmailMessage.to == email, EmailMessage.kind == "alert")
            )
        )
    assert len([m for m in sent if "gas" in m.dedupe_key]) == 1


def test_production_turns_the_interactive_docs_off(settings):
    off = create_app(settings.model_copy(update={"docs_enabled": False}))
    paths = {getattr(r, "path", None) for r in off.routes}
    assert "/docs" not in paths and "/openapi.json" not in paths
    on = create_app(settings)
    assert "/docs" in {getattr(r, "path", None) for r in on.routes}

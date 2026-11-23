"""Reading scale tickets with AI (docs/adr/0038): the model reads, the API checks, a person
decides. Runs after the sale tests: it leaves a recorded sale behind."""

import base64
import uuid

import pytest
from sqlalchemy import select

from zyrcle_api.models import TicketScan
from zyrcle_api.tickets import TicketLine, TicketRead, checks, propose_bags

from .helpers import OPS, sign_in, wait_state
from .test_chain_e2e import deposit
from .test_sale import fill_and_seal

pytestmark = pytest.mark.integration
PNG = base64.b64encode(bytes.fromhex("89504e470d0a1a0a")).decode()  # a stand-in photo


def reading(lines: list[dict], total: float | None, **over) -> dict:
    return {
        "readable": True,
        "center_name": "Centro de acopio La 80",
        "ticket_ref": "T-5521",
        "date": "2026-11-23",
        "lines": lines,
        "total_cop": total,
        "notes": "",
        **over,
    }


def test_the_arithmetic_and_the_gaps_are_flagged_for_the_operator():
    good = TicketRead.model_validate(
        reading(
            [
                {
                    "material": "pet",
                    "label": "PET",
                    "kg": 1.5,
                    "cop_per_kg": 1000,
                    "amount_cop": 1500,
                }
            ],
            1500,
        )
    )
    assert checks(good) == []
    bad = TicketRead(
        readable=True,
        center_name=None,
        ticket_ref=None,
        date="23/11/2026",
        lines=[
            TicketLine(material="pet", label="PET", kg=2, cop_per_kg=1000, amount_cop=3000),
            TicketLine(
                material="other", label="Tetra Pak", kg=None, cop_per_kg=None, amount_cop=200
            ),
        ],
        total_cop=9999,
        notes="",
    )
    kinds = [c["kind"] for c in checks(bad)]
    assert kinds.count("missing") == 3  # ticket number, date, the second line's kilos
    assert kinds.count("arithmetic") == 2  # 2 x 1000 is not 3000; the lines do not add to the total
    assert "material" in kinds


def test_each_line_gets_the_closest_sealed_bag_of_its_material_once():
    read = TicketRead.model_validate(
        reading(
            [
                {"material": "pet", "label": "PET", "kg": 2.0, "cop_per_kg": None, "amount_cop": 1},
                {
                    "material": "pet",
                    "label": "PET 2",
                    "kg": 0.5,
                    "cop_per_kg": None,
                    "amount_cop": 1,
                },
                {
                    "material": "glass",
                    "label": "Vidrio",
                    "kg": 1.0,
                    "cop_per_kg": None,
                    "amount_cop": 1,
                },
            ],
            None,
        )
    )
    sealed = [
        {"code": "A", "material": "pet", "grams": 600},
        {"code": "B", "material": "pet", "grams": 1900},
        {"code": "C", "material": "hdpe", "grams": 1000},
    ]
    assert propose_bags(read, sealed) == ["B", "A", None]


async def test_a_ticket_photo_becomes_a_prefilled_sale_that_a_person_records(
    app, client, settings, bin4, collector, anthropic_api
):
    person = await sign_in(client, settings)
    s = await deposit(client, person, bin4, "pet", "pet_bottle", 3)
    await wait_state(client, person, s["id"], "verified")
    bag = await fill_and_seal(client, collector, bin4, "pet")
    kg = bag["grams"] / 1000
    anthropic_api.reading = reading(
        [
            {
                "material": "pet",
                "label": "PET botella",
                "kg": kg,
                "cop_per_kg": 1000,
                "amount_cop": round(kg * 1000),
            }
        ],
        round(kg * 1000),
        ticket_ref=f"T-{uuid.uuid4().hex[:6]}",
    )
    r = await client.post(
        "/v1/operator/ticket-scans",
        headers=OPS,
        json={"image_base64": PNG, "media_type": "image/png"},
    )
    assert r.status_code == 201, r.text
    scan = r.json()
    assert scan["status"] == "read" and scan["checks"] == [] and scan["created_by"] == "token"
    assert bag["code"] in scan["proposed_bags"]

    # What reached the model: the photo, the fixed schema, Opus 5.5, and the refusal fallback.
    sent = anthropic_api.requests[-1]
    body = sent["body"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["messages"][0]["content"][0]["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": PNG,
    }
    assert "server-side-fallback-2026-07-01" in sent["headers"]["anthropic-beta"]

    line = scan["reading"]["lines"][0]
    sale = await client.post(
        "/v1/operator/sales",
        headers=OPS,
        json={
            "buyer": scan["reading"]["center_name"],
            "ticket_ref": scan["reading"]["ticket_ref"],
            "sold_on": scan["reading"]["date"],
            "ticket_scan_id": scan["id"],
            "lines": [
                {
                    "bag": bag["code"],
                    "buyer_g": round(line["kg"] * 1000),
                    "amount_cop": line["amount_cop"],
                }
            ],
        },
    )
    assert sale.status_code == 201, sale.text
    async with app.state.maker() as db:
        row = await db.scalar(select(TicketScan).where(TicketScan.id == uuid.UUID(scan["id"])))
    assert (
        row is not None
        and str(row.sale_id) == sale.json()["id"]
        and row.image.startswith(b"\x89PNG")
    )
    image = await client.get(f"/v1/operator/ticket-scans/{scan['id']}/image", headers=OPS)
    assert image.headers["content-type"] == "image/png"


async def test_a_declined_or_missing_reading_keeps_the_photo_and_says_so(
    app, client, anthropic_api
):
    anthropic_api.refuse = True
    try:
        r = await client.post(
            "/v1/operator/ticket-scans",
            headers=OPS,
            json={"image_base64": PNG, "media_type": "image/png"},
        )
    finally:
        anthropic_api.refuse = False
    assert r.status_code == 201 and r.json()["status"] == "failed"
    assert "declined" in r.json()["error"]

    reader, app.state.ticket_reader = app.state.ticket_reader, None
    try:
        off = await client.post(
            "/v1/operator/ticket-scans",
            headers=OPS,
            json={"image_base64": PNG, "media_type": "image/png"},
        )
    finally:
        app.state.ticket_reader = reader
    assert off.status_code == 503
    not_b64 = await client.post(
        "/v1/operator/ticket-scans",
        headers=OPS,
        json={"image_base64": "no!", "media_type": "image/png"},
    )
    assert not_b64.status_code == 422

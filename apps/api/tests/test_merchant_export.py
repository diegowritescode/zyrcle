"""A merchant's accounting export (docs/adr/0045): what goes in, what stays out, the local days,
both formats, and who may ask for it."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from openpyxl import load_workbook

from zyrcle_api.models import PaymentRequest, RedemptionRequest

from .helpers import OPS, headers, sign_in

pytestmark = pytest.mark.integration

TX = "0x" + "ab" * 32


async def merchant(client, settings, name: str) -> dict:
    shop = await sign_in(client, settings)
    r = await client.post(
        "/v1/operator/merchants",
        headers=OPS,
        json={"address": shop["address"], "name": name, "nit": "900123456-7"},
    )
    assert r.status_code == 201, r.text
    return shop


def charge(merchant_id: str, status: str, paid_at: datetime | None, amount: int, concept: str):
    return PaymentRequest(
        merchant_id=uuid.UUID(merchant_id),
        amount_cop=amount,
        concept=concept,
        status=status,
        tx_hash=TX if status == "paid" else None,
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        paid_at=paid_at,
    )


def redemption(merchant_id: str, status: str, at: datetime, amount: int, **extra):
    return RedemptionRequest(
        merchant_id=uuid.UUID(merchant_id),
        amount_cop=amount,
        status=status,
        request_tx=TX if status != "requested" else None,
        created_at=at,
        updated_at=at + timedelta(days=2),
        **extra,
    )


@pytest.fixture
async def shop(app, client, settings) -> dict:
    """A merchant with a month of movements in November 2026, Bogotá time (UTC-5)."""
    shop = await merchant(client, settings, "Café =Central")
    other = await merchant(client, settings, "Otra tienda")
    me = shop["id"]
    async with app.state.maker() as db:
        db.add_all(
            [
                # In: 1 Nov at 00:30 in Bogotá, 05:30 UTC.
                charge(me, "paid", datetime(2026, 11, 1, 5, 30, tzinfo=UTC), 5_000, "Almuerzo"),
                # In: 30 Nov 23:30 in Bogotá is 1 Dec 04:30 UTC.
                charge(me, "paid", datetime(2026, 12, 1, 4, 30, tzinfo=UTC), 2_500, "=1+1"),
                # Out: 31 Oct 23:59 in Bogotá.
                charge(me, "paid", datetime(2026, 11, 1, 4, 59, tzinfo=UTC), 9_999, "Octubre"),
                # Out: never paid.
                charge(me, "open", None, 1_000, "Sin pagar"),
                charge(me, "expired", None, 1_000, "Vencido"),
                # Out: another merchant's.
                charge(other["id"], "paid", datetime(2026, 11, 10, tzinfo=UTC), 7_000, "Ajeno"),
                redemption(
                    me,
                    "settled",
                    datetime(2026, 11, 20, 15, tzinfo=UTC),
                    4_000,
                    bank_ref="TRF-001",
                    decision_tx="0x" + "cd" * 32,
                    decided_by="ops@example.org",
                ),
                redemption(me, "pending", datetime(2026, 11, 25, 15, tzinfo=UTC), 1_500),
                redemption(
                    me,
                    "refunded",
                    datetime(2026, 11, 26, 15, tzinfo=UTC),
                    800,
                    decision_tx="0x" + "ef" * 32,
                ),
                # Out: their ZYR never left the account.
                redemption(me, "requested", datetime(2026, 11, 27, 15, tzinfo=UTC), 600),
                redemption(me, "failed", datetime(2026, 11, 27, 16, tzinfo=UTC), 700),
            ]
        )
        await db.commit()
    return shop


NOVEMBER = {"start": "2026-11-01", "end": "2026-11-30"}


async def test_the_csv_has_what_moved_in_the_local_month_and_nothing_else(client, shop):
    r = await client.get("/v1/merchant/export", params=NOVEMBER, headers=headers(shop))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == (
        'attachment; filename="zyrcle-cafe-central-2026-11-01-a-2026-11-30.csv"'
    )
    assert r.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    header, body = rows[0], rows[1:]
    assert header[:4] == ["Fecha", "Tipo", "Estado", "Valor (COP)"]
    seen = [(row[1], row[2], int(row[3])) for row in body]
    assert seen == [
        ("Cobro", "pagado", 5_000),
        ("Canje", "transferido", 4_000),
        ("Canje", "pendiente de transferencia", 1_500),
        ("Canje", "devuelto", 800),
        ("Cobro", "pagado", 2_500),
    ]
    first, settled, last = body[0], body[1], body[-1]
    assert first[0] == "2026-11-01 00:30"  # Bogotá time, not UTC
    assert last[0] == "2026-11-30 23:30"
    # A concept or a name that starts like a formula is text to the spreadsheet.
    assert last[4] == "'=1+1"
    assert last[10] == "Café =Central"
    assert last[11] == "900123456-7"
    assert settled[7] == "2026-11-22 10:00" and settled[8] == "TRF-001"
    assert settled[6] == TX and settled[9] == "0x" + "cd" * 32


async def test_the_excel_file_has_the_same_rows_typed_and_totalled(client, shop):
    r = await client.get(
        "/v1/merchant/export", params={**NOVEMBER, "format": "xlsx"}, headers=headers(shop)
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"].endswith('.xlsx"')
    sheet = load_workbook(io.BytesIO(r.content)).active
    values = [[c.value for c in row] for row in sheet.iter_rows()]
    assert values[0][0] == "Zyrcle · Café =Central"
    assert values[1][0] == "NIT 900123456-7"
    header = values.index(next(v for v in values if v[0] == "Fecha"))
    body = [v for v in values[header + 1 :] if v[1] in ("Cobro", "Canje")]
    assert [v[3] for v in body] == [5_000, 4_000, 1_500, 800, 2_500]
    # The formula-looking concept is stored as text, without the CSV's apostrophe.
    formula_cell = sheet.cell(row=header + 1 + len(body), column=5)
    assert formula_cell.value == "=1+1" and formula_cell.data_type == "s"
    totals = {v[0]: v[3] for v in values if v[0] and v[0].startswith(("Cobros", "Canjes"))}
    assert totals == {
        "Cobros pagados": 7_500,
        "Canjes transferidos": 4_000,
        "Canjes pendientes de transferencia": 1_500,
    }


async def test_the_operator_gets_any_merchants_export_from_the_console(client, shop):
    r = await client.get(
        f"/v1/operator/merchants/{shop['id']}/export", params=NOVEMBER, headers=OPS
    )
    assert r.status_code == 200, r.text
    assert len(list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))) == 6
    r = await client.get(
        f"/v1/operator/merchants/{uuid.uuid4()}/export", params=NOVEMBER, headers=OPS
    )
    assert r.status_code == 404
    r = await client.get(f"/v1/operator/merchants/{shop['id']}/export", params=NOVEMBER)
    assert r.status_code == 401


async def test_a_switched_off_merchant_still_gets_their_records(client, shop):
    r = await client.post(
        "/v1/operator/merchants",
        headers=OPS,
        json={
            "address": shop["address"],
            "name": "Café =Central",
            "nit": "900123456-7",
            "active": False,
        },
    )
    assert r.status_code == 201, r.text
    r = await client.get("/v1/merchant/export", params=NOVEMBER, headers=headers(shop))
    assert r.status_code == 200
    assert r.content.count(b"\r\n") == 6


async def test_only_merchants_and_sensible_ranges(client, settings, shop):
    someone = await sign_in(client, settings)
    r = await client.get("/v1/merchant/export", params=NOVEMBER, headers=headers(someone))
    assert r.status_code == 403
    backwards = {"start": "2026-11-30", "end": "2026-11-01"}
    r = await client.get("/v1/merchant/export", params=backwards, headers=headers(shop))
    assert r.status_code == 422
    too_long = {"start": "2025-01-01", "end": "2026-11-30"}
    r = await client.get("/v1/merchant/export", params=too_long, headers=headers(shop))
    assert r.status_code == 422
    r = await client.get(
        "/v1/merchant/export", params={**NOVEMBER, "format": "pdf"}, headers=headers(shop)
    )
    assert r.status_code == 422
    empty = {"start": "2026-01-01", "end": "2026-01-31"}
    r = await client.get("/v1/merchant/export", params=empty, headers=headers(shop))
    assert r.status_code == 200 and r.content.count(b"\r\n") == 1

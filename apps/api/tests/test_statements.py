"""Bank statements (docs/adr/0039): read any bank's export, propose, a person confirms. Runs after
the sale tests: it confirms a sale on chain."""

import base64
import io
import uuid
from datetime import date, datetime, timedelta

import pytest

from zyrcle_api.bank import StatementUnreadable, parse_amount, parse_date, parse_statement, propose

from .helpers import OPS, sign_in, wait_state
from .test_chain_e2e import deposit
from .test_sale import fill_and_seal, host_with_address, wait_line

pytestmark = pytest.mark.integration


def test_colombian_and_other_number_formats():
    assert parse_amount("1.234.567,00") == 1_234_567
    assert parse_amount("$ 20.000") == 20_000
    assert parse_amount("-20,000.00") == -20_000
    assert parse_amount("(1.500)") == -1_500
    assert parse_amount("2500,5") == 2_500
    assert parse_amount(1500.0) == 1_500
    assert parse_amount("") is None
    assert parse_date("23/11/2026") == date(2026, 11, 23)
    assert parse_date("2026-11-23") == date(2026, 11, 23)
    assert parse_date("20261123") == date(2026, 11, 23)
    assert parse_date(datetime(2026, 11, 23, 9)) == date(2026, 11, 23)


def test_a_semicolon_csv_with_credit_and_debit_columns():
    csv = (
        "Extracto cuenta de ahorros\n"
        "Fecha;Descripción;Documento;Débito;Crédito;Saldo\n"
        "23/11/2026;TRANSF CENTRO LA 80 T-0001;8812;;20.000,00;120.000,00\n"
        "23/11/2026;PAGO CAFETERIA CENTRAL;8813;2.000,00;;118.000,00\n"
        "Total;;;;;\n"
    ).encode("latin-1")
    rows = parse_statement("movimientos.csv", csv)
    assert [(r.amount_cop, r.reference) for r in rows] == [(20_000, "8812"), (-2_000, "8813")]
    assert rows[0].description == "TRANSF CENTRO LA 80 T-0001"


def test_an_excel_export_with_one_signed_amount_column():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Movimientos"])
    ws.append(["FECHA", "DESCRIPCION", "REFERENCIA", "VALOR"])
    ws.append([datetime(2026, 11, 24), "ABONO TRANSFERENCIA", "REF-9", 35000])
    ws.append([datetime(2026, 11, 24), "RETIRO", "REF-10", -1500])
    out = io.BytesIO()
    wb.save(out)
    rows = parse_statement("extracto.xlsx", out.getvalue())
    assert [r.amount_cop for r in rows] == [35_000, -1_500]


def test_a_file_without_dates_and_amounts_is_refused_with_a_reason():
    with pytest.raises(StatementUnreadable, match="encabezados"):
        parse_statement("x.csv", b"a,b,c\n1,2,3\n")


def test_proposals_pick_the_same_amount_near_the_date_and_prefer_the_ticket_number():
    day = date(2026, 11, 23)
    lines = [
        {
            "id": "L1",
            "posted_on": day,
            "description": "ABONO",
            "reference": "",
            "amount_cop": 20_000,
        },
        {
            "id": "L2",
            "posted_on": day,
            "description": "TRANSF T-0001",
            "reference": "",
            "amount_cop": 20_000,
        },
        {
            "id": "L3",
            "posted_on": day + timedelta(days=30),
            "description": "T-0002",
            "reference": "",
            "amount_cop": 9_000,
        },
        {
            "id": "L4",
            "posted_on": day,
            "description": "PAGO CAFETERIA CENTRAL",
            "reference": "",
            "amount_cop": -2_000,
        },
    ]
    sales = [
        {
            "id": "S1",
            "total_cop": 20_000,
            "sold_on": day,
            "ticket_ref": "T-0001",
            "buyer": "Centro La 80",
        },
        {"id": "S2", "total_cop": 9_000, "sold_on": day, "ticket_ref": "T-0002", "buyer": "Otro"},
    ]
    redemptions = [
        {
            "id": "R1",
            "amount_cop": 2_000,
            "requested_on": day,
            "merchant": "Cafetería Central",
            "tax_id": "900",
        }
    ]
    found = {(p.kind, p.target_id): p for p in propose(lines, sales, redemptions)}
    assert found[("sale", "S1")].line_id == "L2"  # the line that names the ticket wins
    assert ("sale", "S2") not in found  # the only line of that amount is a month late
    assert found[("redemption", "R1")].line_id == "L4"
    assert "nombra al comercio" in found[("redemption", "R1")].why


async def test_uploading_a_statement_proposes_the_match_and_one_click_confirms_the_sale(
    client, settings, bin4, collector
):
    person = await sign_in(client, settings)
    s = await deposit(client, person, bin4, "pet", "pet_bottle", 3)
    await wait_state(client, person, s["id"], "verified")
    bag = await fill_and_seal(client, collector, bin4, "pet")
    await host_with_address(client)
    ticket = f"T-{uuid.uuid4().hex[:6].upper()}"
    sale = (
        await client.post(
            "/v1/operator/sales",
            headers=OPS,
            json={
                "buyer": "Centro de acopio La 80",
                "ticket_ref": ticket,
                "sold_on": date.today().isoformat(),
                "lines": [{"bag": bag["code"], "buyer_g": bag["grams"], "amount_cop": 7_777}],
            },
        )
    ).json()
    today = date.today().strftime("%d/%m/%Y")
    csv = f'Fecha,Descripcion,Referencia,Valor\n{today},TRANSF {ticket},REF-{ticket},"7.777,00"\n'
    upload = {"filename": "banco.csv", "content_base64": base64.b64encode(csv.encode()).decode()}
    r = await client.post("/v1/operator/bank-statements", headers=OPS, json=upload)
    assert r.status_code == 201, r.text
    assert r.json()["added"] == 1
    proposal = next(p for p in r.json()["proposals"] if p["target_id"] == sale["id"])
    assert proposal["kind"] == "sale" and "nombra el tiquete" in proposal["why"]

    again = await client.post("/v1/operator/bank-statements", headers=OPS, json=upload)
    assert again.json()["added"] == 0 and again.json()["already_known"] == 1

    m = await client.post(
        f"/v1/operator/bank-lines/{proposal['line']['id']}/match",
        headers=OPS,
        json={"kind": "sale", "target_id": sale["id"]},
    )
    assert m.status_code == 200, m.text
    assert m.json()["matched_by"] == "token"
    done = await wait_line(client, sale["id"], "settled", "failed")
    assert done["status"] == "confirmed" and done["bank_ref"] == f"REF-{ticket}"
    twice = await client.post(
        f"/v1/operator/bank-lines/{proposal['line']['id']}/match",
        headers=OPS,
        json={"kind": "sale", "target_id": sale["id"]},
    )
    assert twice.status_code == 409
    assert sale["id"] not in {
        p["target_id"]
        for p in (await client.get("/v1/operator/bank-proposals", headers=OPS)).json()
    }

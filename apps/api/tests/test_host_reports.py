"""A host's monthly report, goals and ranking figures (docs/adr/0046): the report issued and
emailed once with its PDF, the settings behind it, progress against goals, and the GreenMetric
workbook."""

import base64
import io
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from zyrcle_api.mail import EmailWorker
from zyrcle_api.models import EmailMessage
from zyrcle_api.monthly_reports import REPORTER, MonthlyReportWorker, previous_period

from .helpers import OPS, wait_for
from .test_impact import sell_one_bag

pytestmark = pytest.mark.integration


def test_the_previous_month_crosses_the_year():
    assert previous_period(datetime(2027, 1, 3)) == "2026-12"
    assert previous_period(datetime(2026, 12, 1)) == "2026-11"


def next_month_day(settings, day: int) -> datetime:
    """10:00 on `day` of next month, local time: the worker then reports this month."""
    now = datetime.now(ZoneInfo(settings.timezone))
    return (now.replace(day=1) + timedelta(days=32)).replace(
        day=day, hour=10, minute=0, second=0, microsecond=0
    )


async def university(client) -> dict:
    return next(
        h for h in (await client.get("/v1/hosts")).json() if h["name"] == "Universidad del Río"
    )


async def test_the_report_needs_an_email_and_keeps_them_clean(client, devices):
    host = await university(client)
    url = f"/v1/operator/hosts/{host['id']}/reporting"
    r = await client.put(url, headers=OPS, json={"monthly_report": True, "report_emails": []})
    assert r.status_code == 422
    r = await client.put(
        url, headers=OPS, json={"monthly_report": True, "report_emails": ["no es un correo"]}
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_email"
    r = await client.put(
        url,
        headers=OPS,
        json={
            "monthly_report": False,
            "report_emails": [" Rectoria@Example.org", "rectoria@example.org"],
            "monthly_goal_kg": 50,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["report_emails"] == ["rectoria@example.org"]
    assert r.json()["monthly_goal_kg"] == 50
    got = (await client.get(url, headers=OPS)).json()
    assert got["monthly_report"] is False and got["sites"]
    assert (await client.get(url)).status_code == 401
    r = await client.put(
        f"/v1/operator/hosts/{uuid.uuid4()}/reporting",
        headers=OPS,
        json={"monthly_report": False},
    )
    assert r.status_code == 404


async def test_the_monthly_report_is_issued_once_waits_for_the_anchor_and_mails_the_pdf(
    app, client, settings, chain_env, bin4, collector, resend
):
    await sell_one_bag(client, settings, bin4, collector, [6, 3])
    host = await university(client)
    emails = ["rectoria@example.org", "sostenibilidad@example.org"]
    r = await client.put(
        f"/v1/operator/hosts/{host['id']}/reporting",
        headers=OPS,
        json={"monthly_report": True, "report_emails": emails, "monthly_goal_kg": 50},
    )
    assert r.status_code == 200, r.text
    # A host with nothing sold gets no certificate and no email.
    empty = (
        await client.post(
            "/v1/operator/hosts",
            headers=OPS,
            json={"name": "Conjunto Vacío", "kind": "residential"},
        )
    ).json()
    await client.put(
        f"/v1/operator/hosts/{empty['id']}/reporting",
        headers=OPS,
        json={"monthly_report": True, "report_emails": ["admin@vacio.example"]},
    )

    def worker(day: int) -> MonthlyReportWorker:
        moment = next_month_day(settings, day)
        return MonthlyReportWorker(app.state.maker, settings, app.state.impact, lambda: moment)

    # After the first days, nothing is issued.
    assert await worker(8).run_once() == 0
    reporting = (await client.get(f"/v1/operator/hosts/{host['id']}/reporting", headers=OPS)).json()
    assert reporting["reports"] == []

    first = worker(1)
    assert await first.run_once() >= 2
    reporting = (await client.get(f"/v1/operator/hosts/{host['id']}/reporting", headers=OPS)).json()
    report = reporting["reports"][0]
    assert report["status"] == "waiting" and report["period"] == previous_period(
        next_month_day(settings, 1)
    )
    certificate = (await client.get(f"/v1/certificates/{report['certificate_id']}")).json()
    assert certificate["issued_by"] == REPORTER and certificate["site"] is None
    other = (await client.get(f"/v1/operator/hosts/{empty['id']}/reporting", headers=OPS)).json()
    assert other["reports"][0]["status"] == "empty"
    assert other["reports"][0]["certificate_id"] is None

    async def anchored() -> bool:
        got = await client.get(f"/v1/certificates/{report['certificate_id']}")
        return got.json()["status"] == "anchored"

    await wait_for(anchored, timeout=20)
    await first.run_once()
    await first.run_once()  # a second pass sends nothing more
    reporting = (await client.get(f"/v1/operator/hosts/{host['id']}/reporting", headers=OPS)).json()
    assert reporting["reports"][0]["status"] == "sent"
    assert reporting["reports"][0]["recipients"] == 2

    # The outbox is dated by the worker's clock; deliver it at that moment.
    mailer = app.state.emails._mail
    await EmailWorker(app.state.maker, mailer, lambda: next_month_day(settings, 1)).run_once(50)
    for to in emails:
        sent = [e for e in resend.to(to) if "Certificado de impacto" in e["subject"]]
        assert len(sent) == 1, to
        mail = sent[0]
        assert host["name"] in mail["subject"]
        assert f"/certificates/{report['certificate_id']}" in mail["text"]
        (attachment,) = mail["attachments"]
        assert attachment["content_type"] == "application/pdf"
        assert attachment["filename"].startswith("zyrcle-certificado-universidad-del-rio-")
        assert base64.b64decode(attachment["content"]).startswith(b"%PDF")
    assert not resend.to("admin@vacio.example")
    async with app.state.maker() as db:
        kept = await db.scalars(
            select(EmailMessage.attachments).where(EmailMessage.kind == "monthly_report")
        )
        assert all(a is None for a in kept), "a sent email keeps no copy of the PDF"

    # The same PDF, for anyone, from the certificate.
    r = await client.get(f"/v1/certificates/{report['certificate_id']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith('inline; filename="zyrcle-certificado-')
    assert r.content.startswith(b"%PDF")
    assert (await client.get(f"/v1/certificates/{uuid.uuid4()}/pdf")).status_code == 404

    # Opted out, the host gets no more.
    await client.put(
        f"/v1/operator/hosts/{host['id']}/reporting",
        headers=OPS,
        json={"monthly_report": False, "report_emails": emails},
    )


async def test_progress_compares_sites_against_their_goals(client, settings, bin4, collector):
    await sell_one_bag(client, settings, bin4, collector, [5])
    host = await university(client)
    reporting = (await client.get(f"/v1/operator/hosts/{host['id']}/reporting", headers=OPS)).json()
    site = next(s for s in reporting["sites"] if s["name"] == "Campus de recolección")
    r = await client.put(
        f"/v1/operator/sites/{site['id']}/goal", headers=OPS, json={"monthly_goal_kg": 2}
    )
    assert r.status_code == 200 and r.json()["monthly_goal_kg"] == 2

    progress = (await client.get(f"/v1/hosts/{host['id']}/progress")).json()
    assert progress["period"] == datetime.now(ZoneInfo(settings.timezone)).strftime("%Y-%m")
    assert len(progress["months"]) == 6 and progress["months"][-1]["period"] == progress["period"]
    mine = next(s for s in progress["sites"] if s["id"] == site["id"])
    assert mine["kg"] > 0 and mine["participants"] >= 1
    assert mine["progress_pct"] == round(mine["kg"] * 100 / 2)
    assert mine["kg_per_participant"] is not None
    assert mine["months"][-1]["kg"] == mine["kg"]
    # The host's figure counts a person once across sites, and is never less than a site's.
    assert progress["kg"] >= mine["kg"] and progress["participants"] >= mine["participants"]
    kgs = [s["kg"] for s in progress["sites"]]
    assert kgs == sorted(kgs, reverse=True)

    await client.put(f"/v1/operator/sites/{site['id']}/goal", headers=OPS, json={})
    progress = (await client.get(f"/v1/hosts/{host['id']}/progress", params={"months": 3})).json()
    assert len(progress["months"]) == 3
    assert next(s for s in progress["sites"] if s["id"] == site["id"])["progress_pct"] is None
    assert (await client.get(f"/v1/hosts/{uuid.uuid4()}/progress")).status_code == 404
    r = await client.put(
        f"/v1/operator/sites/{site['id']}/goal", headers=OPS, json={"monthly_goal_kg": 0}
    )
    assert r.status_code == 422


async def test_the_greenmetric_workbook_backs_each_figure(client, settings, bin4, collector):
    await sell_one_bag(client, settings, bin4, collector, [4])
    host = await university(client)
    year = datetime.now(ZoneInfo(settings.timezone)).year
    url = f"/v1/operator/hosts/{host['id']}/greenmetric"
    r = await client.get(url, params={"year": year}, headers=OPS)
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == (
        f'attachment; filename="zyrcle-greenmetric-universidad-del-rio-{year}.xlsx"'
    )
    book = load_workbook(io.BytesIO(r.content))
    assert book.sheetnames == ["Resumen", "Por mes", "Por material", "Certificados"]
    summary = [[c.value for c in row] for row in book["Resumen"].iter_rows()]
    assert "no es el total de residuos" in summary[2][0]
    figures = {(row[0], row[1]): row[2] for row in summary if row[0] and row[0].startswith("WS")}
    assert figures[("WS.1 Programa 3R", "Personas que reciclaron")] >= 1
    recycled_pet = figures[
        ("WS.4 Residuos inorgánicos", "PET: reciclado (vendido a un centro de acopio)")
    ]
    assert recycled_pet > 0
    assert figures[("WS.2 Papel y plástico", "Plástico (PET y HDPE) reciclado")] >= recycled_pet
    months = [[c.value for c in row] for row in book["Por mes"].iter_rows(min_row=2)]
    assert len(months) == 12 and sum(m[2] for m in months) == pytest.approx(
        figures[("WS.4 Residuos inorgánicos", "Total reciclado (vendido a un centro de acopio)")],
        abs=0.2,
    )
    evidence = list(book["Certificados"].iter_rows(min_row=2, values_only=True))
    for row in evidence:
        assert row[5].startswith(settings.public_web_url + "/certificates/")

    assert (await client.get(url, params={"year": year + 1}, headers=OPS)).status_code == 422
    assert (await client.get(url, params={"year": year})).status_code == 401

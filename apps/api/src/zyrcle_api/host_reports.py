"""What a host sees beyond its dashboard (docs/adr/0046): progress against its monthly goals with
a comparison between its sites, and the yearly figures for sustainability rankings such as UI
GreenMetric, each backed by Zyrcle's own records.

Kilograms "recovered" are the credited deposits (verified by the container or approved by an
operator), counted in the local month they were made, like the dashboard. Kilograms "sold to a
recycler" are those whose bag's sale settled, counted in the month it settled, like the
certificates.
"""

import io
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from .certificate_pdf import MATERIALS, verify_url
from .domain.impact import FACTORS_VERSION, co2e_g
from .domain.session_machine import CREDITED
from .ipfs import gateway_url
from .models import Certificate, CollectionFill, Container, DepositSession, Host, SaleLine, Site

CREDITED_STATES = [s.value for s in CREDITED]
PLASTICS = ("pet", "hdpe")


def _kg(grams: int | None) -> float:
    return round((grams or 0) / 1000, 1)


def _periods(local: datetime, months: int) -> list[str]:
    """The last `months` months up to `local`'s, oldest first, as YYYY-MM."""
    out = []
    year, month = local.year, local.month
    for _ in range(months):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return out[::-1]


def _local_month(tz: ZoneInfo, column):
    return func.to_char(func.timezone(tz.key, column), "YYYY-MM")


def _pct(kg: float, goal: int | None) -> int | None:
    return round(kg * 100 / goal) if goal else None


async def host_progress(
    db: AsyncSession, host: Host, tz: ZoneInfo, now: datetime, months: int = 6
) -> dict[str, Any]:
    """This month's kilograms against the host's and each site's goal, and the last `months`
    months of each site, so sites compare by total, per participant and trend."""
    periods = _periods(now.astimezone(tz), months)
    first = datetime.strptime(periods[0] + "-01", "%Y-%m-%d").replace(tzinfo=tz)
    sites = list(await db.scalars(select(Site).where(Site.host_id == host.id).order_by(Site.name)))
    month = _local_month(tz, DepositSession.created_at)
    credited = and_(
        DepositSession.state.in_(CREDITED_STATES),
        DepositSession.created_at >= first,
        Container.site_id.in_([s.id for s in sites]),
    )
    per_site = await db.execute(
        select(
            Container.site_id,
            month,
            func.coalesce(func.sum(DepositSession.deposited_g), 0),
            func.count(distinct(DepositSession.resident_id)),
        )
        .join(Container, Container.id == DepositSession.container_id)
        .where(credited)
        .group_by(Container.site_id, month)
    )
    # A person who recycles at two sites counts once for the host.
    per_host = await db.execute(
        select(
            month,
            func.coalesce(func.sum(DepositSession.deposited_g), 0),
            func.count(distinct(DepositSession.resident_id)),
        )
        .join(Container, Container.id == DepositSession.container_id)
        .where(credited)
        .group_by(month)
    )
    site_months: dict[tuple[uuid.UUID, str], tuple[int, int]] = {
        (site_id, period): (int(grams), people) for site_id, period, grams, people in per_site
    }
    host_months = {period: (int(grams), people) for period, grams, people in per_host}
    current = periods[-1]

    def series(lookup) -> list[dict[str, Any]]:
        return [
            {"period": p, "kg": _kg(lookup(p)[0]), "participants": lookup(p)[1]} for p in periods
        ]

    site_views = []
    for s in sites:
        grams, people = site_months.get((s.id, current), (0, 0))
        site_views.append(
            {
                "id": str(s.id),
                "name": s.name,
                "goal_kg": s.monthly_goal_kg,
                "kg": _kg(grams),
                "participants": people,
                "kg_per_participant": _kg(grams // people) if people else None,
                "progress_pct": _pct(_kg(grams), s.monthly_goal_kg),
                "months": series(lambda p, s=s: site_months.get((s.id, p), (0, 0))),
            }
        )
    grams, people = host_months.get(current, (0, 0))
    return {
        "host": {"id": str(host.id), "name": host.name},
        "timezone": tz.key,
        "period": current,
        "goal_kg": host.monthly_goal_kg,
        "kg": _kg(grams),
        "participants": people,
        "progress_pct": _pct(_kg(grams), host.monthly_goal_kg),
        "months": series(lambda p: host_months.get(p, (0, 0))),
        "sites": sorted(site_views, key=lambda v: (-v["kg"], v["name"])),
    }


# ---------------------------------------------------------------------- rankings


async def _year_figures(db: AsyncSession, host_id: uuid.UUID, year: int, tz: ZoneInfo):
    start = datetime(year, 1, 1, tzinfo=tz)
    end = datetime(year + 1, 1, 1, tzinfo=tz)
    month = _local_month(tz, DepositSession.created_at)
    received = list(
        await db.execute(
            select(
                month,
                DepositSession.declared_material,
                func.coalesce(func.sum(DepositSession.deposited_g), 0),
                func.count(DepositSession.id),
            )
            .join(Container, Container.id == DepositSession.container_id)
            .join(Site, Site.id == Container.site_id)
            .where(
                Site.host_id == host_id,
                DepositSession.state.in_(CREDITED_STATES),
                DepositSession.created_at >= start,
                DepositSession.created_at < end,
            )
            .group_by(month, DepositSession.declared_material)
        )
    )
    people = await db.scalar(
        select(func.count(distinct(DepositSession.resident_id)))
        .join(Container, Container.id == DepositSession.container_id)
        .join(Site, Site.id == Container.site_id)
        .where(
            Site.host_id == host_id,
            DepositSession.state.in_(CREDITED_STATES),
            DepositSession.created_at >= start,
            DepositSession.created_at < end,
        )
    )
    people_by_month = dict(
        list(
            await db.execute(
                select(month, func.count(distinct(DepositSession.resident_id)))
                .join(Container, Container.id == DepositSession.container_id)
                .join(Site, Site.id == Container.site_id)
                .where(
                    Site.host_id == host_id,
                    DepositSession.state.in_(CREDITED_STATES),
                    DepositSession.created_at >= start,
                    DepositSession.created_at < end,
                )
                .group_by(month)
            )
        )
    )
    # Sold: the same join the certificates use (impact.py), without the claim check.
    sold_deposits = (
        select(
            DepositSession.id,
            DepositSession.declared_material,
            DepositSession.deposited_g,
            _local_month(tz, SaleLine.settled_at).label("month"),
        )
        .join(
            CollectionFill,
            and_(
                CollectionFill.collection_id == DepositSession.collection_id,
                CollectionFill.material == DepositSession.declared_material,
                CollectionFill.bag_id.is_not(None),
            ),
        )
        .join(SaleLine, SaleLine.bag_id == CollectionFill.bag_id)
        .join(Container, Container.id == DepositSession.container_id)
        .join(Site, Site.id == Container.site_id)
        .where(
            Site.host_id == host_id,
            SaleLine.status == "settled",
            SaleLine.settled_at >= start,
            SaleLine.settled_at < end,
            DepositSession.state.in_(CREDITED_STATES),
            DepositSession.deposited_g > 0,
        )
        .ext(distinct_on(DepositSession.id))
        .subquery()
    )
    sold = list(
        await db.execute(
            select(
                sold_deposits.c.month,
                sold_deposits.c.declared_material,
                func.sum(sold_deposits.c.deposited_g),
            ).group_by(sold_deposits.c.month, sold_deposits.c.declared_material)
        )
    )
    return received, int(people or 0), people_by_month, sold


async def greenmetric_export(
    db: AsyncSession,
    host: Host,
    year: int,
    tz: ZoneInfo,
    now: datetime,
    web_url: str,
    gateway: str,
) -> bytes:
    """An Excel workbook with the year's figures that UI GreenMetric's Waste (WS) questionnaire
    asks for and Zyrcle can back, by month and by material, and the certificates as evidence."""
    received, people, people_by_month, sold = await _year_figures(db, host.id, year, tz)
    certificates = list(
        await db.execute(
            select(Certificate, Site)
            .outerjoin(Site, Site.id == Certificate.site_id)
            .where(Certificate.host_id == host.id, Certificate.period.like(f"{year:04d}-%"))
            .order_by(Certificate.period, Certificate.created_at)
        )
    )
    received_by_material: dict[str, int] = {}
    received_by_month: dict[str, int] = {}
    deposits_by_month: dict[str, int] = {}
    for period, material, grams, count in received:
        received_by_material[material] = received_by_material.get(material, 0) + int(grams)
        received_by_month[period] = received_by_month.get(period, 0) + int(grams)
        deposits_by_month[period] = deposits_by_month.get(period, 0) + count
    sold_by_material: dict[str, int] = {}
    sold_by_month: dict[str, int] = {}
    for period, material, grams in sold:
        sold_by_material[material] = sold_by_material.get(material, 0) + int(grams)
        sold_by_month[period] = sold_by_month.get(period, 0) + int(grams)
    materials = sorted(set(received_by_material) | set(sold_by_material))
    sold_total = sum(sold_by_material.values())
    co2e_total = sum(co2e_g(m, g) for m, g in sold_by_material.items())

    book = Workbook()
    bold = Font(bold=True)
    summary = book.active
    summary.title = "Resumen"
    made = now.astimezone(tz)
    for line, strong in (
        (f"Zyrcle · Datos para UI GreenMetric · {host.name} · {year}", True),
        (f"Generado el {made:%Y-%m-%d %H:%M} (hora de {tz.key}).", False),
        (
            "Solo cuenta lo que pasó por los contenedores de Zyrcle: no es el total de residuos de "
            "la institución.",
            False,
        ),
        (
            "Indicadores de la categoría Residuos (WS) revisados el 2026-11-27 en fuentes "
            "públicas: WS.1 programa 3R, WS.2 reducción de papel y plástico, WS.4 tratamiento "
            "de residuos inorgánicos. Confírmelos en el cuestionario del año.",
            False,
        ),
        (
            "Zyrcle no registra campañas: los participantes y depósitos son los de todo el año.",
            False,
        ),
    ):
        summary.append([line])
        cell = summary.cell(row=summary.max_row, column=1)
        cell.data_type = "s"
        if strong:
            cell.font = bold
    summary.append([])
    summary.append(["Indicador", "Dato", "Valor", "Unidad", "Evidencia"])
    for cell in summary[summary.max_row]:
        cell.font = bold
    rows: list[list[Any]] = [
        ["WS.1 Programa 3R", "Personas que reciclaron", people, "personas", "Hoja «Por mes»"],
        [
            "WS.1 Programa 3R",
            "Depósitos verificados",
            sum(deposits_by_month.values()),
            "depósitos",
            "Hoja «Por mes»",
        ],
    ]
    for m in materials:
        label = MATERIALS.get(m, m)
        rows.append(
            [
                "WS.4 Residuos inorgánicos",
                f"{label}: recibido y verificado en los contenedores",
                _kg(received_by_material.get(m)),
                "kg",
                "Hoja «Por material»",
            ]
        )
        rows.append(
            [
                "WS.4 Residuos inorgánicos",
                f"{label}: reciclado (vendido a un centro de acopio)",
                _kg(sold_by_material.get(m)),
                "kg",
                "Hoja «Certificados»",
            ]
        )
    rows += [
        [
            "WS.4 Residuos inorgánicos",
            "Total reciclado (vendido a un centro de acopio)",
            _kg(sold_total),
            "kg",
            "Hoja «Certificados»",
        ],
        [
            "WS.2 Papel y plástico",
            "Plástico (PET y HDPE) reciclado",
            _kg(sum(sold_by_material.get(m, 0) for m in PLASTICS)),
            "kg",
            "Hoja «Por material»",
        ],
        [
            "Informativo",
            f"CO2e evitado por lo reciclado (EPA WARM v16, {FACTORS_VERSION}; no es un crédito)",
            _kg(co2e_total),
            "kg CO2e",
            "Hoja «Certificados»",
        ],
    ]
    for row in rows:
        summary.append(row)

    by_month = book.create_sheet("Por mes")
    by_month.append(
        ["Mes", "Recibido y verificado (kg)", "Reciclado (kg)", "Personas", "Depósitos"]
    )
    for cell in by_month[1]:
        cell.font = bold
    for p in [f"{year:04d}-{m:02d}" for m in range(1, 13)]:
        by_month.append(
            [
                p,
                _kg(received_by_month.get(p)),
                _kg(sold_by_month.get(p)),
                people_by_month.get(p, 0),
                deposits_by_month.get(p, 0),
            ]
        )

    by_material = book.create_sheet("Por material")
    by_material.append(["Material", "Recibido y verificado (kg)", "Reciclado (kg)", "CO2e (kg)"])
    for cell in by_material[1]:
        cell.font = bold
    for m in materials:
        sold_g = sold_by_material.get(m, 0)
        by_material.append(
            [
                MATERIALS.get(m, m),
                _kg(received_by_material.get(m)),
                _kg(sold_g),
                _kg(co2e_g(m, sold_g)),
            ]
        )

    evidence = book.create_sheet("Certificados")
    evidence.append(
        [
            "Mes",
            "Sede",
            "Reciclado (kg)",
            "CO2e (kg)",
            "Estado",
            "Verificación",
            "Copia en IPFS",
            "Transacción",
        ]
    )
    for cell in evidence[1]:
        cell.font = bold
    for c, site in certificates:
        url = verify_url(web_url, str(c.id))
        evidence.append(
            [
                c.period,
                site.name if site else "Todas las sedes",
                _kg(c.grams),
                _kg(c.co2e_g),
                "anclado" if c.status == "anchored" else "pendiente de anclar",
                url,
                gateway_url(gateway, c.ipfs_cid) or "",
                c.anchor_tx or "",
            ]
        )
        evidence.cell(row=evidence.max_row, column=6).hyperlink = url
    for sheet, widths in (
        (summary, (28, 62, 12, 12, 22)),
        (by_month, (10, 26, 16, 12, 12)),
        (by_material, (14, 26, 16, 12)),
        (evidence, (10, 22, 16, 12, 20, 70, 70, 68)),
    ):
        for i, width in enumerate(widths):
            sheet.column_dimensions[chr(ord("A") + i)].width = width
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()

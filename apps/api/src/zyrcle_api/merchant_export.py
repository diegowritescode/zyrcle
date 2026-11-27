"""A merchant's accounting export (docs/adr/0045): the charges participants paid and the
redemptions of ZYR for pesos in a date range, as CSV or Excel, for the merchant's bookkeeping.

One row per movement. A charge counts when it was paid; a redemption counts when it was requested,
because that is when its ZYR left the merchant's account, and the row says whether the pesos were
transferred (and when, with the bank's reference) or the ZYR came back. Charges that were never
paid and redemptions that never reached the chain moved nothing and are left out.
"""

import csv
import io
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Merchant, PaymentRequest, RedemptionRequest

Format = Literal["csv", "xlsx"]
MAX_DAYS = 366
MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
REDEMPTION_STATUS = {
    "pending": "pendiente de transferencia",
    "settled": "transferido",
    "refunded": "devuelto",
}
COLUMNS = (
    "Fecha",
    "Tipo",
    "Estado",
    "Valor (COP)",
    "Concepto",
    "Referencia Zyrcle",
    "Transacción",
    "Fecha de transferencia",
    "Referencia bancaria",
    "Transacción de cierre",
    "Comercio",
    "NIT",
)


@dataclass(frozen=True)
class Movement:
    at: datetime
    kind: Literal["Cobro", "Canje"]
    status: str
    amount_cop: int
    concept: str
    reference: str
    tx: str | None
    transferred_at: datetime | None = None
    bank_ref: str | None = None
    closing_tx: str | None = None


@dataclass(frozen=True)
class Export:
    filename: str
    media_type: str
    content: bytes


def period_bounds(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The local days `start` to `end`, both included, as an instant range [from, to)."""
    if end < start:
        raise ValueError("the end date is before the start date")
    if (end - start).days >= MAX_DAYS:
        raise ValueError(f"at most {MAX_DAYS} days per export")
    return (
        datetime.combine(start, time.min, tz),
        datetime.combine(end + timedelta(days=1), time.min, tz),
    )


async def movements(
    db: AsyncSession, merchant_id: uuid.UUID, since: datetime, until: datetime
) -> list[Movement]:
    charges = await db.scalars(
        select(PaymentRequest).where(
            PaymentRequest.merchant_id == merchant_id,
            PaymentRequest.status == "paid",
            PaymentRequest.paid_at >= since,
            PaymentRequest.paid_at < until,
        )
    )
    redemptions = await db.scalars(
        select(RedemptionRequest).where(
            RedemptionRequest.merchant_id == merchant_id,
            RedemptionRequest.status.in_(tuple(REDEMPTION_STATUS)),
            RedemptionRequest.created_at >= since,
            RedemptionRequest.created_at < until,
        )
    )
    rows = [
        Movement(
            at=p.paid_at,
            kind="Cobro",
            status="pagado",
            amount_cop=p.amount_cop,
            concept=p.concept,
            reference=str(p.id),
            tx=p.tx_hash,
        )
        for p in charges
        if p.paid_at is not None
    ] + [
        Movement(
            at=r.created_at,
            kind="Canje",
            status=REDEMPTION_STATUS[r.status],
            amount_cop=r.amount_cop,
            concept="Canje de ZYR por pesos",
            reference=str(r.id),
            tx=r.request_tx,
            transferred_at=r.updated_at if r.status == "settled" else None,
            bank_ref=r.bank_ref,
            closing_tx=r.decision_tx,
        )
        for r in redemptions
    ]
    return sorted(rows, key=lambda m: (m.at, m.reference))


def _safe(text: str | None) -> str:
    """Free text a spreadsheet must not run: a cell that starts with = + - @ (or a tab or a
    return) is a formula to Excel and LibreOffice, so it gets a leading apostrophe."""
    text = text or ""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _plain(text: str | None) -> str:
    """Free text for an Excel cell: control characters, which the file format cannot hold, out."""
    return ILLEGAL_CHARACTERS_RE.sub("", text or "")


def _local(at: datetime | None, tz: ZoneInfo) -> str:
    return at.astimezone(tz).strftime("%Y-%m-%d %H:%M") if at else ""


def _cells(m: Movement, merchant: Merchant, tz: ZoneInfo, for_csv: bool) -> list[str | int]:
    # Excel cells are typed as text below, so only the CSV needs the apostrophe.
    text = _safe if for_csv else _plain
    return [
        _local(m.at, tz),
        m.kind,
        m.status,
        m.amount_cop,
        text(m.concept),
        m.reference,
        m.tx or "",
        _local(m.transferred_at, tz),
        text(m.bank_ref),
        m.closing_tx or "",
        text(merchant.name),
        text(merchant.nit),
    ]


def totals(rows: list[Movement]) -> list[tuple[str, int]]:
    def total(kind: str, status: str) -> int:
        return sum(m.amount_cop for m in rows if m.kind == kind and m.status == status)

    return [
        ("Cobros pagados", total("Cobro", "pagado")),
        ("Canjes transferidos", total("Canje", "transferido")),
        ("Canjes pendientes de transferencia", total("Canje", "pendiente de transferencia")),
    ]


def filename(merchant: Merchant, start: date, end: date, fmt: Format) -> str:
    ascii_name = unicodedata.normalize("NFKD", merchant.name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40] or "comercio"
    return f"zyrcle-{slug}-{start.isoformat()}-a-{end.isoformat()}.{fmt}"


def render(
    merchant: Merchant,
    rows: list[Movement],
    start: date,
    end: date,
    fmt: Format,
    tz: ZoneInfo,
    now: datetime,
) -> Export:
    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow(COLUMNS)
        writer.writerows(_cells(m, merchant, tz, for_csv=True) for m in rows)
        # The byte order mark tells Excel the file is UTF-8, so the accents survive.
        content = ("﻿" + out.getvalue()).encode("utf-8")
    else:
        content = _xlsx(merchant, rows, start, end, tz, now)
    return Export(filename(merchant, start, end, fmt), MEDIA_TYPES[fmt], content)


def _xlsx(
    merchant: Merchant,
    rows: list[Movement],
    start: date,
    end: date,
    tz: ZoneInfo,
    now: datetime,
) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Movimientos"
    bold = Font(bold=True)
    head = [
        (f"Zyrcle · {merchant.name}", True),
        (f"NIT {merchant.nit}", False),
        (f"Del {start.isoformat()} al {end.isoformat()} (hora de {tz.key})", False),
        (f"Generado el {_local(now, tz)}", False),
    ]
    for text, strong in head:
        sheet.append([text])
        cell = sheet.cell(row=sheet.max_row, column=1)
        cell.data_type = "s"  # never a formula, whatever the merchant's name says
        if strong:
            cell.font = bold
    sheet.append([])
    sheet.append(list(COLUMNS))
    for cell in sheet[sheet.max_row]:
        cell.font = bold
    header_row = sheet.max_row
    for m in rows:
        sheet.append(_cells(m, merchant, tz, for_csv=False))
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"  # text typed by people never runs as a formula
        sheet.cell(row=sheet.max_row, column=4).number_format = "#,##0"
    sheet.append([])
    for label, value in totals(rows):
        sheet.append([label, None, None, value])
        sheet.cell(row=sheet.max_row, column=1).font = bold
        sheet.cell(row=sheet.max_row, column=4).number_format = "#,##0"
    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
    widths = (17, 8, 26, 12, 30, 38, 68, 20, 22, 68, 24, 14)
    for i, width in enumerate(widths):
        sheet.column_dimensions[chr(ord("A") + i)].width = width
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


async def export(
    db: AsyncSession,
    merchant: Merchant,
    start: date,
    end: date,
    fmt: Format,
    tz: ZoneInfo,
    now: datetime,
) -> Export:
    since, until = period_bounds(start, end, tz)
    rows = await movements(db, merchant.resident_id, since, until)
    return render(merchant, rows, start, end, fmt, tz, now)

"""The monthly report (docs/adr/0046): in the first days of each month, the previous month's
impact certificate of every host that opted in, issued without anyone asking, and emailed as a
formal PDF to the host's contacts once its root is anchored on ZyrcleChain (and its public copy is
on IPFS, when Pinata is configured: the anchor waits for the copy).

One row per host and month (`monthly_report`) keeps it to once:

    waiting (certificate issued, anchor pending) -> sent | failed;   empty: nothing sold that month
"""

import base64
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .certificate_pdf import kg, month_name, pdf_filename, render_certificate, verify_url
from .config import Settings
from .impact import ImpactService, utcnow
from .mail import enqueue_email, render_html
from .models import Certificate, Host, MonthlyReport

log = logging.getLogger(__name__)
REPORTER = "el informe mensual automático"
FOOTER = (
    "Recibe este correo porque su institución pidió a Zyrcle el informe mensual. Para dejar de "
    "recibirlo o cambiar a quién llega, escríbale al equipo de Zyrcle."
)


def previous_period(local: datetime) -> str:
    """The month before `local`'s, as YYYY-MM."""
    year, month = (local.year, local.month - 1) if local.month > 1 else (local.year - 1, 12)
    return f"{year:04d}-{month:02d}"


def report_email(certificate: dict[str, Any], web_url: str) -> tuple[str, str, str]:
    """Subject, text and HTML of the email that carries the PDF."""
    place = certificate["host"]["name"]
    month = month_name(certificate["period"])
    url = verify_url(web_url, certificate["id"])
    people = certificate["participants"]
    lines = [
        f"Adjuntamos el certificado de impacto de {place} por el material vendido en {month}: "
        f"{kg(certificate['grams'])} recuperados y vendidos a un reciclador, "
        f"{kg(certificate['co2e_g'])} de CO2e evitado, de {people} "
        + ("persona." if people == 1 else "personas."),
        f"Cualquiera puede verificarlo en {url}: el navegador recalcula la huella de cada depósito "
        "y la compara con la que quedó escrita en ZyrcleChain.",
        "Cuenta solo lo que pasó por los contenedores de Zyrcle, no el total de residuos de la "
        "institución.",
    ]
    subject = f"Certificado de impacto de {month} · {place}"
    text = "\n\n".join([*lines, FOOTER])
    return subject, text, render_html(f"Su certificado de {month}", lines, footer=FOOTER)


class MonthlyReportWorker:
    def __init__(
        self,
        maker: async_sessionmaker[AsyncSession],
        settings: Settings,
        impact: ImpactService,
        clock: Callable[[], datetime] = utcnow,
    ):
        self._maker = maker
        self._settings = settings
        self._tz = ZoneInfo(settings.timezone)
        self._impact = impact
        self._now = clock

    async def run_once(self) -> int:
        now = self._now()
        local = now.astimezone(self._tz)
        done = 0
        # Only in the first days: a host that opts in on the 15th gets its first report next month.
        if local.day <= self._settings.monthly_report_last_day:
            done += await self._issue(previous_period(local), now)
        return done + await self._send(now)

    async def _issue(self, period: str, now: datetime) -> int:
        async with self._maker() as db:
            hosts = list(
                await db.scalars(
                    select(Host.id).where(
                        Host.monthly_report.is_(True),
                        ~exists().where(
                            MonthlyReport.host_id == Host.id, MonthlyReport.period == period
                        ),
                    )
                )
            )
        for host_id in hosts:
            certificate_id = await self._certificate_for(host_id, period)
            async with self._maker() as db:
                db.add(
                    MonthlyReport(
                        id=uuid.uuid4(),
                        host_id=host_id,
                        period=period,
                        status="waiting" if certificate_id else "empty",
                        certificate_id=certificate_id,
                        created_at=now,
                    )
                )
                try:
                    await db.commit()
                except IntegrityError:
                    continue  # another run made it a moment ago
            log.info("monthly report %s %s: %s", host_id, period, certificate_id or "nothing sold")
        return len(hosts)

    async def _certificate_for(self, host_id: uuid.UUID, period: str) -> uuid.UUID | None:
        """A new certificate for what is left to certify in the month; else the latest one already
        issued for the whole host (by an operator, or by a run that stopped before its row was
        written); else nothing: no material was sold that month."""
        preview = await self._impact.preview(host_id, None, period)
        if preview["deposits"] > 0:
            issued = await self._impact.issue(host_id, None, period, REPORTER)
            return uuid.UUID(issued["id"])
        async with self._maker() as db:
            return await db.scalar(
                select(Certificate.id)
                .where(
                    Certificate.host_id == host_id,
                    Certificate.site_id.is_(None),
                    Certificate.period == period,
                    Certificate.status != "failed",
                )
                .order_by(Certificate.created_at.desc())
                .limit(1)
            )

    async def _send(self, now: datetime) -> int:
        async with self._maker() as db:
            rows = list(
                await db.execute(
                    select(MonthlyReport, Certificate, Host)
                    .join(Certificate, Certificate.id == MonthlyReport.certificate_id)
                    .join(Host, Host.id == MonthlyReport.host_id)
                    .where(
                        MonthlyReport.status == "waiting",
                        Certificate.status.in_(("anchored", "failed")),
                    )
                    .with_for_update(of=MonthlyReport, skip_locked=True)
                )
            )
            for report, certificate, host in rows:
                if certificate.status == "failed":
                    report.status, report.last_error = "failed", "the certificate's anchor failed"
                    continue
                if not host.report_emails:
                    report.status, report.last_error = "failed", "the host has no report emails"
                    continue
                view = await self._impact.get(certificate.id, with_leaves=False)
                pdf = render_certificate(
                    view, self._settings.public_web_url, self._settings.chain_id, self._tz, now
                )
                subject, text, html_body = report_email(view, self._settings.public_web_url)
                attachment = {
                    "filename": pdf_filename(view),
                    "content_type": "application/pdf",
                    "content_b64": base64.b64encode(pdf).decode(),
                }
                for to in host.report_emails:
                    await enqueue_email(
                        db,
                        to=to,
                        kind="monthly_report",
                        dedupe_key=f"monthly-report:{report.id}:{to}",
                        subject=subject,
                        text=text,
                        html_body=html_body,
                        now=now,
                        attachments=[attachment],
                    )
                report.status, report.sent_at = "sent", now
                report.recipients = len(host.report_emails)
            await db.commit()
        return len(rows)

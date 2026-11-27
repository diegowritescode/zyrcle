"""A host's monthly report, goals and ranking figures (docs/adr/0046): operators configure them
and download the GreenMetric workbook; anyone reads a host's progress, like its dashboard."""

import uuid
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import utcnow
from .deps import Operator
from .email_codes import normalize_email
from .errors import InvalidEmail
from .filenames import slug
from .host_reports import greenmetric_export, host_progress
from .models import Host, MonthlyReport, Site

router = APIRouter(prefix="/v1", tags=["reports"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ReportingIn(BaseModel):
    monthly_report: bool
    report_emails: list[str] = Field(default_factory=list, max_length=10)
    monthly_goal_kg: int | None = Field(default=None, ge=1, le=10_000_000)


class GoalIn(BaseModel):
    monthly_goal_kg: int | None = Field(default=None, ge=1, le=10_000_000)


def _tz(request: Request) -> ZoneInfo:
    return ZoneInfo(request.app.state.settings.timezone)


async def _host(db, host_id: uuid.UUID) -> Host:
    host = await db.get(Host, host_id)
    if host is None:
        raise HTTPException(404, {"code": "not_found", "detail": "unknown host"})
    return host


async def _reporting_view(db, host: Host) -> dict[str, Any]:
    sites = await db.scalars(select(Site).where(Site.host_id == host.id).order_by(Site.name))
    reports = await db.scalars(
        select(MonthlyReport)
        .where(MonthlyReport.host_id == host.id)
        .order_by(MonthlyReport.period.desc())
        .limit(12)
    )
    return {
        "host_id": str(host.id),
        "monthly_report": host.monthly_report,
        "report_emails": host.report_emails,
        "monthly_goal_kg": host.monthly_goal_kg,
        "sites": [
            {"id": str(s.id), "name": s.name, "monthly_goal_kg": s.monthly_goal_kg} for s in sites
        ],
        "reports": [
            {
                "period": r.period,
                "status": r.status,
                "certificate_id": str(r.certificate_id) if r.certificate_id else None,
                "recipients": r.recipients,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "last_error": r.last_error,
            }
            for r in reports
        ],
    }


@router.get("/operator/hosts/{host_id}/reporting")
async def get_reporting(host_id: uuid.UUID, _: Operator, request: Request) -> dict[str, Any]:
    """The host's monthly report settings, its goals, and its last twelve reports."""
    async with request.app.state.maker() as db:
        return await _reporting_view(db, await _host(db, host_id))


@router.put("/operator/hosts/{host_id}/reporting")
async def set_reporting(
    host_id: uuid.UUID, body: ReportingIn, _: Operator, request: Request
) -> dict[str, Any]:
    """Opt the host in or out of the monthly report, set who receives it, and its monthly goal."""
    try:
        emails = list(dict.fromkeys(normalize_email(e) for e in body.report_emails))
    except InvalidEmail as e:
        raise HTTPException(422, {"code": e.code, "detail": e.detail}) from None
    if body.monthly_report and not emails:
        raise HTTPException(
            422, {"code": "invalid", "detail": "the monthly report needs at least one email"}
        )
    async with request.app.state.maker() as db:
        host = await _host(db, host_id)
        host.monthly_report, host.report_emails = body.monthly_report, emails
        host.monthly_goal_kg = body.monthly_goal_kg
        await db.commit()
        return await _reporting_view(db, host)


@router.put("/operator/sites/{site_id}/goal")
async def set_site_goal(
    site_id: uuid.UUID, body: GoalIn, _: Operator, request: Request
) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        site = await db.get(Site, site_id)
        if site is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown site"})
        site.monthly_goal_kg = body.monthly_goal_kg
        await db.commit()
        return {"id": str(site.id), "name": site.name, "monthly_goal_kg": site.monthly_goal_kg}


@router.get("/hosts/{host_id}/progress")
async def progress(
    host_id: uuid.UUID, request: Request, months: int = Query(default=6, ge=1, le=12)
) -> dict[str, Any]:
    """This month's kilograms against the goals, and each site's last months. Public, like the
    dashboard: totals only, never a person."""
    async with request.app.state.maker() as db:
        return await host_progress(db, await _host(db, host_id), _tz(request), utcnow(), months)


@router.get("/operator/hosts/{host_id}/greenmetric")
async def greenmetric(
    host_id: uuid.UUID,
    _: Operator,
    request: Request,
    year: int = Query(ge=2025, le=2100),
) -> Response:
    """The year's figures for UI GreenMetric's Waste questionnaire, as Excel (docs/adr/0046)."""
    settings = request.app.state.settings
    tz = _tz(request)
    now = utcnow()
    if year > now.astimezone(tz).year:
        raise HTTPException(422, {"code": "invalid", "detail": "that year has not started"})
    async with request.app.state.maker() as db:
        host = await _host(db, host_id)
        content = await greenmetric_export(
            db, host, year, tz, now, settings.public_web_url, settings.ipfs_gateway
        )
    name = f"zyrcle-greenmetric-{slug(host.name, 'institucion')}-{year}.xlsx"
    return Response(
        content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )

"""Public, read-only views: platform totals, residences and containers.

Traceability is the product, so the aggregates are public: anyone can see how many kilos each
residence recycled and how many pesos were paid for them. Nothing here identifies a resident, and
no access code is ever exposed (those only appear on the container's own screen).
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import Date, cast, distinct, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import utcnow
from .config import Settings
from .domain.session_machine import ACTIVE, CREDITED
from .models import Container, DepositSession, Device, Payout, Residence

router = APIRouter(prefix="/v1", tags=["public"])

CREDITED_STATES = [s.value for s in CREDITED]
ACTIVE_STATES = [s.value for s in ACTIVE]


def is_online(device: Device, now: datetime, settings: Settings) -> bool:
    return bool(
        device.last_seen_at
        and (now - device.last_seen_at).total_seconds() < settings.device_offline_after_s
    )


async def busy_containers(db: AsyncSession) -> set[str]:
    return set(
        await db.scalars(
            select(DepositSession.container_id).where(DepositSession.state.in_(ACTIVE_STATES))
        )
    )


def _kg(grams: int | None) -> float:
    return round((grams or 0) / 1000, 3)


async def _totals(db: AsyncSession, residence_id: uuid.UUID | None = None) -> dict[str, Any]:
    deposits = (
        select(
            func.count(DepositSession.id),
            func.coalesce(func.sum(DepositSession.deposited_g), 0),
            func.count(distinct(DepositSession.resident_id)),
        )
        .join(Container, Container.id == DepositSession.container_id)
        .where(DepositSession.state.in_(CREDITED_STATES))
    )
    paid = (
        select(func.count(Payout.id), func.coalesce(func.sum(Payout.amount_cop), 0))
        .join(DepositSession, DepositSession.id == Payout.session_id)
        .join(Container, Container.id == DepositSession.container_id)
        .where(Payout.status == "confirmed")
    )
    containers = select(func.count(Container.id))
    if residence_id is not None:
        deposits = deposits.where(Container.residence_id == residence_id)
        paid = paid.where(Container.residence_id == residence_id)
        containers = containers.where(Container.residence_id == residence_id)
    count, grams, residents = (await db.execute(deposits)).one()
    payouts, cop = (await db.execute(paid)).one()
    return {
        "containers": await db.scalar(containers) or 0,
        "deposits_verified": count,
        "kg_verified": _kg(grams),
        "residents": residents,
        "payouts_confirmed": payouts,
        "paid_cop": int(cop),
    }


def _container_view(
    container: Container, device: Device, now: datetime, settings: Settings, busy: set[str]
) -> dict[str, Any]:
    return {
        "id": container.id,
        "name": container.name,
        "residence_id": str(container.residence_id),
        "accepted_materials": container.accepted_materials,
        "online": is_online(device, now, settings),
        "busy": container.id in busy,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }


@router.get("/stats")
async def stats(request: Request) -> dict[str, Any]:
    """Platform totals: what the landing page shows instead of made-up numbers."""
    async with request.app.state.maker() as db:
        return await _totals(db)


@router.get("/containers/{container_id}")
async def container(container_id: str, request: Request) -> dict[str, Any]:
    """What a resident's app shows after scanning a QR: the container and what it accepts."""
    async with request.app.state.maker() as db:
        row = (
            await db.execute(
                select(Container, Device, Residence)
                .join(Device, Device.id == Container.device_id)
                .join(Residence, Residence.id == Container.residence_id)
                .where(Container.id == container_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown container"})
        busy = await busy_containers(db)
    c, device, residence = row
    view = _container_view(c, device, utcnow(), request.app.state.settings, busy)
    return {**view, "residence_name": residence.name}


@router.get("/residences")
async def residences(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        rows = await db.execute(
            select(Residence, func.count(Container.id))
            .outerjoin(Container, Container.residence_id == Residence.id)
            .group_by(Residence.id)
            .order_by(Residence.created_at)
        )
        return [{"id": str(r.id), "name": r.name, "containers": n} for r, n in rows]


@router.get("/residences/{residence_id}/dashboard")
async def residence_dashboard(
    residence_id: uuid.UUID, request: Request, days: int = Query(default=14, ge=1, le=90)
) -> dict[str, Any]:
    """Everything the residence dashboard draws: totals, each container's state and the daily
    kilos (by declared material) and pesos paid over the last `days` days, in local time."""
    settings: Settings = request.app.state.settings
    tz = ZoneInfo(settings.timezone)
    now = utcnow()
    today = now.astimezone(tz).date()
    first_day = today - timedelta(days=days - 1)
    since = datetime.combine(first_day, datetime.min.time(), tzinfo=tz)

    async with request.app.state.maker() as db:
        residence = await db.get(Residence, residence_id)
        if residence is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown residence"})
        totals = await _totals(db, residence_id)
        busy = await busy_containers(db)
        rows = (
            await db.execute(
                select(Container, Device)
                .join(Device, Device.id == Container.device_id)
                .where(Container.residence_id == residence_id)
                .order_by(Container.id)
            )
        ).all()
        ids = [c.id for c, _ in rows]

        per_container = {
            cid: (n, grams)
            for cid, n, grams in await db.execute(
                select(
                    DepositSession.container_id,
                    func.count(DepositSession.id),
                    func.coalesce(func.sum(DepositSession.deposited_g), 0),
                )
                .where(
                    DepositSession.container_id.in_(ids),
                    DepositSession.state.in_(CREDITED_STATES),
                )
                .group_by(DepositSession.container_id)
            )
        }
        paid_per_container = dict(
            (
                await db.execute(
                    select(DepositSession.container_id, func.sum(Payout.amount_cop))
                    .join(Payout, Payout.session_id == DepositSession.id)
                    .where(DepositSession.container_id.in_(ids), Payout.status == "confirmed")
                    .group_by(DepositSession.container_id)
                )
            ).all()
        )
        # The latest closed lid of each container tells how full it is and what it weighs, whether
        # or not that deposit was paid: rejected material is still physically inside.
        latest = {
            s.container_id: s
            for s in await db.scalars(
                select(DepositSession)
                .ext(distinct_on(DepositSession.container_id))
                .where(
                    DepositSession.container_id.in_(ids),
                    DepositSession.fill_after_mm.is_not(None),
                )
                .order_by(DepositSession.container_id, DepositSession.updated_at.desc())
            )
        }

        local_day = cast(func.timezone(settings.timezone, DepositSession.created_at), Date)
        activity_rows = await db.execute(
            select(
                local_day,
                DepositSession.declared_material,
                func.sum(DepositSession.deposited_g),
            )
            .join(Container, Container.id == DepositSession.container_id)
            .where(
                Container.residence_id == residence_id,
                DepositSession.state.in_(CREDITED_STATES),
                DepositSession.created_at >= since,
            )
            .group_by(local_day, DepositSession.declared_material)
        )
        paid_day = cast(func.timezone(settings.timezone, Payout.updated_at), Date)
        payout_rows = await db.execute(
            select(paid_day, func.sum(Payout.amount_cop))
            .join(DepositSession, DepositSession.id == Payout.session_id)
            .join(Container, Container.id == DepositSession.container_id)
            .where(
                Container.residence_id == residence_id,
                Payout.status == "confirmed",
                Payout.updated_at >= since,
            )
            .group_by(paid_day)
        )

    day_list = [first_day + timedelta(days=i) for i in range(days)]
    kg_by_day: dict[date, dict[str, float]] = {d: {} for d in day_list}
    for day, material, grams in activity_rows:
        if day in kg_by_day:
            kg_by_day[day][material] = _kg(grams)
    cop_by_day: dict[date, int] = {d: 0 for d in day_list}
    for day, cop in payout_rows:
        if day in cop_by_day:
            cop_by_day[day] = int(cop)

    containers = []
    for c, device in rows:
        last = latest.get(c.id)
        fill_pct = None
        weight_kg = None
        if last is not None and last.fill_after_mm is not None:
            fill_pct = round(max(0, min(100, 100 * (c.depth_mm - last.fill_after_mm) / c.depth_mm)))
            weight_kg = _kg(last.final_g)
        deposits, grams = per_container.get(c.id, (0, 0))
        containers.append(
            {
                **_container_view(c, device, now, settings, busy),
                "fill_pct": fill_pct,
                "weight_kg": weight_kg,
                "deposits_verified": deposits,
                "kg_verified": _kg(grams),
                "paid_cop": int(paid_per_container.get(c.id) or 0),
                "last_deposit_at": last.updated_at.isoformat() if last is not None else None,
            }
        )

    return {
        "residence": {"id": str(residence.id), "name": residence.name},
        "timezone": settings.timezone,
        "totals": totals,
        "containers": containers,
        "activity": [{"day": d.isoformat(), "kg": kg_by_day[d]} for d in day_list],
        "payouts": [{"day": d.isoformat(), "cop": cop_by_day[d]} for d in day_list],
    }

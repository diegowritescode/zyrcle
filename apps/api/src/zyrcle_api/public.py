"""Public, read-only views: platform totals, hosts, sites and containers.

Traceability is the product, so the aggregates are public: anyone can see how many kilos each host
and each of its sites recycled and how many pesos were paid for them. Nothing here identifies a
participant, and no access code is ever exposed (those only appear on the container's own screen).

`/v1/residences` and the `residence_*` fields are deprecated aliases of the site routes and fields,
kept while installed apps still read them (docs/adr/0011).
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import Date, String, cast, distinct, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import utcnow
from .config import Settings
from .domain.session_machine import ACTIVE, CREDITED
from .fill import fill_levels
from .models import Container, DepositSession, Device, Host, Payout, SaleLine, Settlement, Site

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


def _settled():
    """Pesos deposits received when their bag was sold, on top of the advance (docs/adr/0013),
    joined to the deposit and its container so callers can filter by site or container."""
    return (
        select(DepositSession.container_id, func.sum(Settlement.paid_cop).label("cop"))
        .join(DepositSession, cast(DepositSession.id, String) == Settlement.party_ref)
        .join(Container, Container.id == DepositSession.container_id)
        .where(Settlement.party == "deposit", Settlement.paid_cop.is_not(None))
    )


async def _totals(db: AsyncSession, site_ids: list[uuid.UUID] | None = None) -> dict[str, Any]:
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
    settled = _settled().group_by(DepositSession.container_id)
    if site_ids is not None:
        deposits = deposits.where(Container.site_id.in_(site_ids))
        paid = paid.where(Container.site_id.in_(site_ids))
        containers = containers.where(Container.site_id.in_(site_ids))
        settled = settled.where(Container.site_id.in_(site_ids))
    count, grams, residents = (await db.execute(deposits)).one()
    payouts, cop = (await db.execute(paid)).one()
    # Paid = advances plus what sales added on top of them.
    cop = int(cop) + sum(int(c or 0) for _, c in await db.execute(settled))
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
        "site_id": str(container.site_id),
        "residence_id": str(container.site_id),  # deprecated alias
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


@router.get("/containers")
async def containers(request: Request) -> list[dict[str, Any]]:
    """Every container, for the app's booking screen. No access codes."""
    now, settings = utcnow(), request.app.state.settings
    async with request.app.state.maker() as db:
        rows = (
            await db.execute(
                select(Container, Device, Site, Host)
                .join(Device, Device.id == Container.device_id)
                .join(Site, Site.id == Container.site_id)
                .join(Host, Host.id == Site.host_id)
                .order_by(Host.name, Site.name, Container.id)
            )
        ).all()
        busy = await busy_containers(db)
    return [
        {**_container_view(c, d, now, settings, busy), **_place(site, host)}
        for c, d, site, host in rows
    ]


@router.get("/containers/{container_id}")
async def container(container_id: str, request: Request) -> dict[str, Any]:
    """What a resident's app shows after scanning a QR: the container and what it accepts."""
    async with request.app.state.maker() as db:
        row = (
            await db.execute(
                select(Container, Device, Site, Host)
                .join(Device, Device.id == Container.device_id)
                .join(Site, Site.id == Container.site_id)
                .join(Host, Host.id == Site.host_id)
                .where(Container.id == container_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown container"})
        busy = await busy_containers(db)
    c, device, site, host = row
    view = _container_view(c, device, utcnow(), request.app.state.settings, busy)
    return {**view, **_place(site, host)}


def _place(site: Site, host: Host) -> dict[str, Any]:
    return {
        "site_name": site.name,
        "host_id": str(host.id),
        "host_name": host.name,
        "residence_name": site.name,  # deprecated alias
    }


def _site_ref(site: Site) -> dict[str, Any]:
    return {"id": str(site.id), "name": site.name}


def _host_ref(host: Host) -> dict[str, Any]:
    return {"id": str(host.id), "name": host.name, "kind": host.kind}


async def _sites_with_counts(db: AsyncSession, host_id: uuid.UUID | None = None):
    query = (
        select(Site, func.count(Container.id))
        .outerjoin(Container, Container.site_id == Site.id)
        .group_by(Site.id)
        .order_by(Site.created_at, Site.name)
    )
    if host_id is not None:
        query = query.where(Site.host_id == host_id)
    return (await db.execute(query)).all()


@router.get("/hosts")
async def hosts(request: Request) -> list[dict[str, Any]]:
    """Every host and its sites."""
    async with request.app.state.maker() as db:
        host_rows = list(await db.scalars(select(Host).order_by(Host.created_at, Host.name)))
        by_host: dict[uuid.UUID, list[dict[str, Any]]] = {h.id: [] for h in host_rows}
        for site, n in await _sites_with_counts(db):
            by_host.setdefault(site.host_id, []).append({**_site_ref(site), "containers": n})
    return [{**_host_ref(h), "sites": by_host[h.id]} for h in host_rows]


@router.get("/sites")
async def sites(request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        rows = (
            await db.execute(
                select(Site, Host, func.count(Container.id))
                .join(Host, Host.id == Site.host_id)
                .outerjoin(Container, Container.site_id == Site.id)
                .group_by(Site.id, Host.id)
                .order_by(Host.name, Site.created_at, Site.name)
            )
        ).all()
    return [{**_site_ref(site), "host": _host_ref(host), "containers": n} for site, host, n in rows]


@router.get("/residences", deprecated=True)
async def residences(request: Request) -> list[dict[str, Any]]:
    """Deprecated alias of /v1/sites, in its old shape."""
    async with request.app.state.maker() as db:
        return [{**_site_ref(s), "containers": n} for s, n in await _sites_with_counts(db)]


def _window(settings: Settings, days: int) -> tuple[list[date], datetime]:
    tz = ZoneInfo(settings.timezone)
    today = utcnow().astimezone(tz).date()
    first_day = today - timedelta(days=days - 1)
    return [first_day + timedelta(days=i) for i in range(days)], datetime.combine(
        first_day, datetime.min.time(), tzinfo=tz
    )


async def _daily(
    db: AsyncSession, settings: Settings, site_ids: list[uuid.UUID], days: int
) -> dict[str, list[dict[str, Any]]]:
    """Daily kilos (by declared material) and pesos paid over the last `days` days, local time."""
    day_list, since = _window(settings, days)
    local_day = cast(func.timezone(settings.timezone, DepositSession.created_at), Date)
    activity_rows = await db.execute(
        select(local_day, DepositSession.declared_material, func.sum(DepositSession.deposited_g))
        .join(Container, Container.id == DepositSession.container_id)
        .where(
            Container.site_id.in_(site_ids),
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
            Container.site_id.in_(site_ids),
            Payout.status == "confirmed",
            Payout.updated_at >= since,
        )
        .group_by(paid_day)
    )
    kg_by_day: dict[date, dict[str, float]] = {d: {} for d in day_list}
    for day, material, grams in activity_rows:
        if day in kg_by_day:
            kg_by_day[day][material] = _kg(grams)
    settled_day = cast(func.timezone(settings.timezone, SaleLine.settled_at), Date)
    settled_rows = await db.execute(
        select(settled_day, func.sum(Settlement.paid_cop))
        .join(SaleLine, SaleLine.id == Settlement.line_id)
        .join(DepositSession, cast(DepositSession.id, String) == Settlement.party_ref)
        .join(Container, Container.id == DepositSession.container_id)
        .where(
            Settlement.party == "deposit",
            Settlement.paid_cop.is_not(None),
            Container.site_id.in_(site_ids),
            SaleLine.settled_at >= since,
        )
        .group_by(settled_day)
    )
    cop_by_day: dict[date, int] = {d: 0 for d in day_list}
    for day, cop in [*payout_rows, *settled_rows]:
        if day in cop_by_day:
            cop_by_day[day] += int(cop or 0)
    return {
        "activity": [{"day": d.isoformat(), "kg": kg_by_day[d]} for d in day_list],
        "payouts": [{"day": d.isoformat(), "cop": cop_by_day[d]} for d in day_list],
    }


@router.get("/hosts/{host_id}/dashboard")
async def host_dashboard(
    host_id: uuid.UUID, request: Request, days: int = Query(default=14, ge=1, le=90)
) -> dict[str, Any]:
    """A host's totals across its sites, each site's totals, and the daily series."""
    settings: Settings = request.app.state.settings
    async with request.app.state.maker() as db:
        host = await db.get(Host, host_id)
        if host is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown host"})
        site_rows = await _sites_with_counts(db, host_id)
        ids = [s.id for s, _ in site_rows]
        totals = await _totals(db, ids)
        per_site = [{**_site_ref(s), "totals": await _totals(db, [s.id])} for s, _ in site_rows]
        series = await _daily(db, settings, ids, days)
    return {
        "host": _host_ref(host),
        "timezone": settings.timezone,
        "totals": totals,
        "sites": per_site,
        **series,
    }


@router.get("/sites/{site_id}/dashboard")
async def site_dashboard(
    site_id: uuid.UUID, request: Request, days: int = Query(default=14, ge=1, le=90)
) -> dict[str, Any]:
    """Everything a site's dashboard draws: totals, each container's state and the daily kilos (by
    declared material) and pesos paid over the last `days` days, in local time."""
    settings: Settings = request.app.state.settings
    now = utcnow()

    async with request.app.state.maker() as db:
        site = await db.get(Site, site_id)
        if site is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown site"})
        host = await db.get(Host, site.host_id)
        assert host is not None
        totals = await _totals(db, [site_id])
        busy = await busy_containers(db)
        rows = (
            await db.execute(
                select(Container, Device)
                .join(Device, Device.id == Container.device_id)
                .where(Container.site_id == site_id)
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
        for cid, cop in await db.execute(
            _settled()
            .where(DepositSession.container_id.in_(ids))
            .group_by(DepositSession.container_id)
        ):
            paid_per_container[cid] = int(paid_per_container.get(cid) or 0) + int(cop or 0)
        # The latest closed lid of each container, a deposit's or a collection's, tells how full it
        # is and what it weighs (docs/adr/0042). Rejected material is still physically inside.
        levels = await fill_levels(db, [c for c, _ in rows])
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
        series = await _daily(db, settings, [site_id], days)

    containers = []
    for c, device in rows:
        last = latest.get(c.id)
        level = levels[c.id]
        deposits, grams = per_container.get(c.id, (0, 0))
        containers.append(
            {
                **_container_view(c, device, now, settings, busy),
                "fill_pct": level.pct,
                "weight_kg": _kg(level.weight_g) if level.weight_g is not None else None,
                "deposits_verified": deposits,
                "kg_verified": _kg(grams),
                "paid_cop": int(paid_per_container.get(c.id) or 0),
                "last_deposit_at": last.updated_at.isoformat() if last is not None else None,
            }
        )

    return {
        "site": _site_ref(site),
        "host": _host_ref(host),
        "residence": _site_ref(site),  # deprecated alias
        "timezone": settings.timezone,
        "totals": totals,
        "containers": containers,
        **series,
    }


@router.get("/residences/{site_id}/dashboard", deprecated=True)
async def residence_dashboard(
    site_id: uuid.UUID, request: Request, days: int = Query(default=14, ge=1, le=90)
) -> dict[str, Any]:
    """Deprecated alias of /v1/sites/{id}/dashboard."""
    return await site_dashboard(site_id, request, days)

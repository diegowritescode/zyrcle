"""How full each container is, and the push that tells collectors to empty it (docs/adr/0042).

The container's distance sensor measures from the lid down to the contents, so the reading shrinks
as it fills. The level used is the latest reading after a lid closed, a deposit's or a collection's;
a collection that closed later than the latest deposit without a reading counts as empty.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from .domain.session_machine import State
from .models import Collection, Collector, Container, DepositSession, Site
from .notifications import enqueue

# Deposits whose material is inside once their lid closed, paid or not.
_MEASURED = [s.value for s in (State.VERIFIED, State.APPROVED, State.REVIEW, State.REJECTED)]


def fill_pct(depth_mm: int, distance_mm: int | None) -> int | None:
    """0 (empty) to 100 (full); None without a reading."""
    if distance_mm is None or depth_mm <= 0:
        return None
    return round(max(0, min(100, 100 * (depth_mm - distance_mm) / depth_mm)))


@dataclass
class FillLevel:
    pct: int | None
    weight_g: int | None  # the scale after that lid closed
    last_emptied_at: datetime | None
    deposits_since: int  # measured deposits not yet taken out by a collection


async def fill_levels(db: AsyncSession, containers: list[Container]) -> dict[str, FillLevel]:
    ids = [c.id for c in containers]
    if not ids:
        return {}
    deposits = {
        s.container_id: s
        for s in await db.scalars(
            select(DepositSession)
            .ext(distinct_on(DepositSession.container_id))
            .where(DepositSession.container_id.in_(ids), DepositSession.fill_after_mm.is_not(None))
            .order_by(DepositSession.container_id, DepositSession.updated_at.desc())
        )
    }
    collections = {
        c.container_id: c
        for c in await db.scalars(
            select(Collection)
            .ext(distinct_on(Collection.container_id))
            .where(Collection.container_id.in_(ids), Collection.state == "closed")
            .order_by(Collection.container_id, Collection.closed_at.desc())
        )
    }
    since = dict(
        (
            await db.execute(
                select(DepositSession.container_id, func.count())
                .where(
                    DepositSession.container_id.in_(ids),
                    DepositSession.collection_id.is_(None),
                    DepositSession.state.in_(_MEASURED),
                )
                .group_by(DepositSession.container_id)
            )
        ).all()
    )
    levels = {}
    for c in containers:
        d, col = deposits.get(c.id), collections.get(c.id)
        emptied_later = (
            col is not None
            and col.closed_at is not None
            and (d is None or col.closed_at > d.updated_at)
        )
        if emptied_later:
            assert col is not None
            pct = fill_pct(c.depth_mm, col.fill_after_mm)
            levels[c.id] = FillLevel(0 if pct is None else pct, col.final_g, col.closed_at, 0)
        else:
            levels[c.id] = FillLevel(
                fill_pct(c.depth_mm, d.fill_after_mm) if d is not None else None,
                d.final_g if d is not None else None,
                col.closed_at if col is not None else None,
                int(since.get(c.id) or 0),
            )
    return levels


async def alert_if_full(
    db: AsyncSession, container: Container, distance_mm: int, threshold: int, now: datetime
) -> int:
    """Push the collectors who serve this container's host once it reaches `threshold`, once per
    collector between two collections. In the caller's transaction (the outbox). Returns how many
    collectors were queued (already-alerted ones included)."""
    pct = fill_pct(container.depth_mm, distance_mm)
    if pct is None or pct < threshold:
        return 0
    site = await db.get(Site, container.site_id)
    assert site is not None
    cycle = await db.scalar(
        select(Collection.id)
        .where(Collection.container_id == container.id, Collection.state == "closed")
        .order_by(Collection.closed_at.desc())
        .limit(1)
    )
    collectors = list(
        await db.scalars(
            select(Collector.resident_id).where(
                Collector.active.is_(True),
                or_(Collector.host_id.is_(None), Collector.host_id == site.host_id),
            )
        )
    )
    for resident_id in collectors:
        await enqueue(
            db,
            resident_id=resident_id,
            kind="container_full",
            dedupe_key="container_full:" + _cycle_key(container.id, cycle, resident_id),
            title=f"{container.name} está al {pct} %",
            body=f"En {site.name}. Vacíalo cuando puedas.",
            data={"url": "/collect", "container_id": container.id},
            now=now,
        )
    return len(collectors)


def _cycle_key(container_id: str, cycle: uuid.UUID | None, resident_id: uuid.UUID) -> str:
    raw = f"{container_id}|{cycle or 'first'}|{resident_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]

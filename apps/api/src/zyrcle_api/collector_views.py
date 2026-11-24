"""What a collector sees besides the collection in progress (docs/adr/0042): their containers,
fullest first, and what each of their collections has paid them."""

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .fill import fill_levels
from .models import Collection, CollectionFill, Collector, Container, SaleLine, Settlement, Site

EARNINGS_MONTHS = 6


async def my_containers(db: AsyncSession, collector: Collector) -> list[dict[str, Any]]:
    """The containers of the collector's host (every host's without one): fullest first, unknown
    last, then the longest since they were emptied."""
    query = select(Container, Site).join(Site, Site.id == Container.site_id)
    if collector.host_id is not None:
        query = query.where(Site.host_id == collector.host_id)
    rows = (await db.execute(query)).all()
    levels = await fill_levels(db, [c for c, _ in rows])
    out = []
    for c, site in rows:
        level = levels[c.id]
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "site": {"id": str(site.id), "name": site.name},
                "accepted_materials": c.accepted_materials,
                "fill_pct": level.pct,
                "last_emptied_at": level.last_emptied_at.isoformat()
                if level.last_emptied_at
                else None,
                "deposits_since": level.deposits_since,
            }
        )
    out.sort(
        key=lambda x: (
            x["fill_pct"] is None,
            -(x["fill_pct"] or 0),
            x["last_emptied_at"] or "",  # never emptied sorts as the oldest
        )
    )
    return out


def split(total: int, weights: list[int]) -> list[int]:
    """`total` in proportion to `weights`, adding up exactly to `total` (largest remainder)."""
    whole = sum(weights)
    if whole == 0 or total == 0:
        return [0] * len(weights)
    parts = [total * w // whole for w in weights]
    order = sorted(range(len(weights)), key=lambda i: -(total * weights[i] % whole))
    for i in order[: total - sum(parts)]:
        parts[i] += 1
    return parts


def _month_start(now: datetime, back: int) -> datetime:
    y, m = now.year, now.month - back
    while m <= 0:
        y, m = y - 1, m + 12
    return now.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


async def earnings(
    db: AsyncSession, collector_id: uuid.UUID, tz: ZoneInfo, now: datetime
) -> dict[str, Any]:
    """Each closed collection of the last months: grams into bags, what it has paid and the grams
    still waiting for a sale. A bag's collector share is split among the collections that filled
    it by their grams, so the collections add up to what the settlement report paid."""
    since = _month_start(now.astimezone(tz), EARNINGS_MONTHS - 1)
    collections = list(
        await db.execute(
            select(Collection, Container.name)
            .join(Container, Container.id == Collection.container_id)
            .where(
                Collection.collector_id == collector_id,
                Collection.state == "closed",
                Collection.closed_at >= since,
            )
            .order_by(Collection.closed_at.desc())
        )
    )
    mine = {c.id for c, _ in collections}
    fills = list(
        await db.scalars(
            select(CollectionFill).where(
                CollectionFill.collection_id.in_(mine),
                CollectionFill.bag_id.is_not(None),
                CollectionFill.end_g.is_not(None),
            )
        )
    )
    bag_ids = {f.bag_id for f in fills}
    # Every collection that filled these bags, older ones included, to split each share right.
    by_bag: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(lambda: defaultdict(int))
    for f in await db.scalars(
        select(CollectionFill).where(
            CollectionFill.bag_id.in_(bag_ids), CollectionFill.end_g.is_not(None)
        )
    ):
        by_bag[f.bag_id][f.collection_id] += f.grams or 0
    paid: dict[uuid.UUID, int] = {}
    for bag_id, cop in await db.execute(
        select(SaleLine.bag_id, Settlement.paid_cop)
        .join(SaleLine, SaleLine.id == Settlement.line_id)
        .where(
            Settlement.party == "collector",
            Settlement.party_ref == str(collector_id),
            Settlement.paid_cop.is_not(None),
            SaleLine.bag_id.in_(bag_ids),
        )
    ):
        paid[bag_id] = paid.get(bag_id, 0) + cop

    earned: dict[uuid.UUID, int] = defaultdict(int)
    pending: dict[uuid.UUID, int] = defaultdict(int)
    grams: dict[uuid.UUID, int] = defaultdict(int)
    for bag_id, per_collection in by_bag.items():
        order = sorted(per_collection, key=str)
        shares = split(paid.get(bag_id, 0), [per_collection[c] for c in order])
        for cid, share in zip(order, shares, strict=True):
            if cid not in mine:
                continue
            grams[cid] += per_collection[cid]
            earned[cid] += share
            if bag_id not in paid:
                pending[cid] += per_collection[cid]

    rows = [
        {
            "id": str(c.id),
            "container_name": name,
            "closed_at": c.closed_at.isoformat() if c.closed_at else None,
            "grams": grams[c.id],
            "earned_cop": earned[c.id],
            "pending_g": pending[c.id],
            "month": c.closed_at.astimezone(tz).strftime("%Y-%m") if c.closed_at else None,
        }
        for c, name in collections
    ]
    months: dict[str, dict[str, int]] = {}
    for back in range(EARNINGS_MONTHS - 1, -1, -1):
        months[_month_start(now.astimezone(tz), back).strftime("%Y-%m")] = {
            "collections": 0,
            "grams": 0,
            "earned_cop": 0,
        }
    for r in rows:
        m = months.get(r["month"] or "")
        if m is not None:
            m["collections"] += 1
            m["grams"] += r["grams"]
            m["earned_cop"] += r["earned_cop"]
    return {
        "collections": rows,
        "months": [{"month": k, **v} for k, v in months.items()],
        "total_cop": sum(r["earned_cop"] for r in rows),
    }

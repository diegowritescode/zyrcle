"""Collection centers and their prices (docs/adr/0037).

Final payments already follow the real sale (docs/adr/0013). What the center's price changes is the
advance: a deposit at a site that sells to a center is advanced against that center's price for
the material, falling back to the general table when the center has none.
"""

import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Bag,
    CenterPrice,
    CollectionCenter,
    Container,
    MaterialPrice,
    Sale,
    SaleLine,
    Site,
)

SUGGESTION_WINDOW = timedelta(days=90)


async def reference_price(db: AsyncSession, container_id: str, material: str) -> int | None:
    """COP per kg that sizes an advance: the center the container's site sells to, else the
    general table. None when neither has a price."""
    center_id = await db.scalar(
        select(Site.center_id)
        .join(Container, Container.site_id == Site.id)
        .where(Container.id == container_id)
    )
    if center_id is not None:
        price = await db.get(CenterPrice, (center_id, material))
        if price is not None:
            return price.cop_per_kg
    general = await db.get(MaterialPrice, material)
    return general.cop_per_kg if general else None


async def suggested_prices(
    db: AsyncSession, center_id: uuid.UUID, now: datetime
) -> dict[str, dict[str, int]]:
    """The median COP per kg the center paid per material in confirmed sales of the last 90 days,
    from the buyer's own weights: {material: {"cop_per_kg", "lines"}}."""
    rows = await db.execute(
        select(Bag.material, SaleLine.amount_cop, SaleLine.buyer_g)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .join(Bag, Bag.id == SaleLine.bag_id)
        .where(
            Sale.center_id == center_id,
            Sale.status == "confirmed",
            Sale.sold_on >= now - SUGGESTION_WINDOW,
            SaleLine.buyer_g > 0,
        )
    )
    by_material: dict[str, list[int]] = {}
    for material, amount, grams in rows:
        by_material.setdefault(material, []).append(amount * 1_000 // grams)
    return {
        m: {"cop_per_kg": int(statistics.median_low(v)), "lines": len(v)}
        for m, v in sorted(by_material.items())
    }


async def center_view(db: AsyncSession, c: CollectionCenter) -> dict[str, Any]:
    prices = await db.scalars(
        select(CenterPrice).where(CenterPrice.center_id == c.id).order_by(CenterPrice.material)
    )
    sites = await db.scalars(select(Site).where(Site.center_id == c.id).order_by(Site.name))
    return {
        "id": str(c.id),
        "name": c.name,
        "tax_id": c.tax_id,
        "address": c.address,
        "contact": c.contact,
        "active": c.active,
        "prices": {
            p.material: {
                "cop_per_kg": p.cop_per_kg,
                "source": p.source,
                "updated_by": p.updated_by,
                "updated_at": p.updated_at.isoformat(),
            }
            for p in prices
        },
        "sites": [{"id": str(s.id), "name": s.name} for s in sites],
    }

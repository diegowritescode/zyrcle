"""What a participant sees of their own deposits (docs/adr/0041): each deposit's steps from the lid
to the settlement, their personal impact, and the push when their material is sold.

A deposit is in a bag when the bag got its material during the deposit's collection: the rule the
settlement (ADR 0013) and the certificates (ADR 0027) use.
"""

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain.impact import FACTORS_VERSION, co2e_g
from .domain.session_machine import CREDITED, State
from .models import (
    Collection,
    CollectionFill,
    Container,
    DepositSession,
    Payout,
    Sale,
    SaleLine,
    SessionEvent,
    Settlement,
)
from .notifications import MATERIAL_NAMES, enqueue, weight

CREDITED_STATES = [s.value for s in CREDITED]
MEASURED = {State.VERIFIED, State.APPROVED, State.REVIEW, State.REJECTED}
STEPS = ("deposited", "verified", "advance", "collected", "sold", "paid")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _step(key: str, status: str, at: datetime | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "at": _iso(at),
        "amount_cop": extra.get("amount_cop"),
        "share_cop": extra.get("share_cop"),
        "tx_hash": extra.get("tx_hash"),
        "note": extra.get("note"),
    }


async def deposit_steps(
    db: AsyncSession, sessions: list[DepositSession], payouts: dict[uuid.UUID, Payout | None]
) -> dict[uuid.UUID, dict[str, Any]]:
    """For each deposit: its steps, and what its sales paid on top of the advance (`settled_cop`,
    None until something was paid). A handful of queries for all of them, never one per deposit."""
    ids = [s.id for s in sessions]
    if not ids:
        return {}
    events: dict[uuid.UUID, dict[str, datetime]] = defaultdict(dict)
    for sid, to_state, kind, at in await db.execute(
        select(SessionEvent.session_id, SessionEvent.to_state, SessionEvent.kind, SessionEvent.at)
        .where(
            SessionEvent.session_id.in_(ids),
            or_(
                SessionEvent.to_state.in_([s.value for s in MEASURED]),
                SessionEvent.kind == "no_advance",
            ),
        )
        .order_by(SessionEvent.at)
    ):
        events[sid][to_state or kind] = at  # the latest of each

    collection_ids = {s.collection_id for s in sessions if s.collection_id is not None}
    closed = dict(
        (
            await db.execute(
                select(Collection.id, Collection.closed_at).where(
                    Collection.id.in_(collection_ids), Collection.state == "closed"
                )
            )
        ).all()
    )
    bags: dict[tuple[uuid.UUID, str], set[uuid.UUID]] = defaultdict(set)
    for cid, material, bag_id in await db.execute(
        select(CollectionFill.collection_id, CollectionFill.material, CollectionFill.bag_id).where(
            CollectionFill.collection_id.in_(collection_ids),
            CollectionFill.bag_id.is_not(None),
            CollectionFill.end_g.is_not(None),
        )
    ):
        bags[(cid, material)].add(bag_id)
    all_bags = {b for group in bags.values() for b in group}
    lines: dict[uuid.UUID, list[Any]] = defaultdict(list)
    for row in await db.execute(
        select(SaleLine.bag_id, SaleLine.status, SaleLine.settled_at, Sale.sold_on, Sale.buyer)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(SaleLine.bag_id.in_(all_bags))
    ):
        lines[row.bag_id].append(row)
    shares: dict[str, list[Settlement]] = defaultdict(list)
    for row in await db.scalars(
        select(Settlement).where(
            Settlement.party == "deposit", Settlement.party_ref.in_([str(i) for i in ids])
        )
    ):
        shares[row.party_ref].append(row)

    out: dict[uuid.UUID, dict[str, Any]] = {}
    for s in sessions:
        rows = shares.get(str(s.id), [])
        paid = [r.paid_cop for r in rows if r.paid_cop is not None]
        settled_cop = sum(paid) if paid else None
        if State(s.state) not in MEASURED:
            out[s.id] = {"steps": [], "settled_cop": settled_cop}
            continue
        mine = [
            line
            for bag in sorted(bags.get((s.collection_id, s.declared_material), set()), key=str)
            for line in lines.get(bag, [])
        ]
        out[s.id] = {
            "steps": _steps(s, payouts.get(s.id), events[s.id], closed, mine, rows),
            "settled_cop": settled_cop,
        }
    return out


def _steps(
    s: DepositSession,
    payout: Payout | None,
    events: dict[str, datetime],
    closed: dict[uuid.UUID, datetime | None],
    lines: list[Any],
    shares: list[Settlement],
) -> list[dict[str, Any]]:
    state = State(s.state)
    steps = [_step("deposited", "done", s.created_at)]
    if state == State.REJECTED:
        steps.append(_step("verified", "failed", events.get("rejected"), note=s.review_note))
        return steps + [_step(k, "skipped") for k in STEPS[2:]]
    if state == State.REVIEW:
        steps.append(_step("verified", "pending", events.get("review")))
        return steps + [_step(k, "pending") for k in STEPS[2:]]
    approved = state == State.APPROVED
    steps.append(
        _step(
            "verified",
            "done",
            events.get("approved" if approved else "verified"),
            note="approved_after_review" if approved else None,
        )
    )

    if payout is None:
        steps.append(_step("advance", "skipped" if "no_advance" in events else "pending"))
    else:
        status = {"confirmed": "done", "failed": "failed"}.get(payout.status, "pending")
        steps.append(
            _step(
                "advance",
                status,
                payout.updated_at if status == "done" else None,
                amount_cop=payout.amount_cop,
                tx_hash=payout.tx_hash,
                note="deferred" if payout.status == "deferred" else None,
            )
        )

    closed_at = closed.get(s.collection_id) if s.collection_id is not None else None
    steps.append(_step("collected", "done" if closed_at else "pending", closed_at))

    if lines:
        first = min(lines, key=lambda line: line.sold_on)
        steps.append(_step("sold", "done", first.sold_on, note=first.buyer))
    else:
        steps.append(_step("sold", "pending"))

    paid = [r.paid_cop for r in shares if r.paid_cop is not None]
    share = sum(r.share_cop for r in shares) if shares else None
    on_top = sum(paid) if paid else None
    settled = [line for line in lines if line.status == "settled"]
    if lines and len(settled) == len(lines) and paid:
        tx = next((r.tx_hash for r in reversed(shares) if r.tx_hash), None)
        steps.append(
            _step(
                "paid",
                "done",
                max(line.settled_at for line in settled),
                amount_cop=on_top,
                share_cop=share,
                tx_hash=tx,
                note="covered_by_advance" if on_top == 0 else None,
            )
        )
    else:
        steps.append(_step("paid", "pending", amount_cop=on_top, share_cop=share))
    return steps


# ------------------------------------------------------------------------------------- impact


async def personal_impact(
    db: AsyncSession, resident_id: uuid.UUID, tz: ZoneInfo, now: datetime, months: int = 12
) -> dict[str, Any]:
    """Verified grams by the month of the deposit, sold grams and CO2e by the month the deposit's
    first sale line settled (ADR 0027's rule and factors), per material; totals over all time."""
    credited = (
        DepositSession.resident_id == resident_id,
        DepositSession.state.in_(CREDITED_STATES),
        DepositSession.deposited_g > 0,
    )
    verified = (
        await db.execute(
            select(
                DepositSession.declared_material,
                DepositSession.deposited_g,
                DepositSession.created_at,
            ).where(*credited)
        )
    ).all()
    sold = (
        await db.execute(
            select(
                DepositSession.id,
                DepositSession.declared_material,
                DepositSession.deposited_g,
                func.min(SaleLine.settled_at),
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
            .where(*credited, SaleLine.status == "settled")
            .group_by(DepositSession.id)
        )
    ).all()

    keys = _last_months(now.astimezone(tz), months)
    month: dict[str, dict[str, dict[str, int]]] = {
        k: defaultdict(lambda: defaultdict(int)) for k in keys
    }
    total: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for material, grams, at in verified:
        total[material]["verified_g"] += grams
        k = at.astimezone(tz).strftime("%Y-%m")
        if k in month:
            month[k][material]["verified_g"] += grams
    for _, material, grams, at in sold:
        total[material]["sold_g"] += grams
        k = at.astimezone(tz).strftime("%Y-%m")
        if k in month:
            month[k][material]["sold_g"] += grams

    def figures(by_material: dict[str, dict[str, int]]) -> dict[str, int]:
        return {
            "verified_g": sum(m["verified_g"] for m in by_material.values()),
            "sold_g": sum(m["sold_g"] for m in by_material.values()),
            "co2e_g": sum(co2e_g(mat, m["sold_g"]) for mat, m in by_material.items()),
        }

    return {
        "factors_version": FACTORS_VERSION,
        "deposits": len(verified),
        "totals": figures(total),
        "materials": [
            {
                "material": mat,
                "verified_g": m["verified_g"],
                "sold_g": m["sold_g"],
                "co2e_g": co2e_g(mat, m["sold_g"]),
            }
            for mat, m in sorted(total.items(), key=lambda kv: -kv[1]["verified_g"])
        ],
        "months": [{"month": k, **figures(month[k])} for k in keys],
    }


def _last_months(now: datetime, count: int) -> list[str]:
    y, m = now.year, now.month
    out = []
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


# ------------------------------------------------------------------------------- sold push


async def notify_sold(db: AsyncSession, bag_ids: list[uuid.UUID], buyer: str, now: datetime) -> int:
    """`deposit_sold` to every credited deposit in these bags, once per deposit (ADR 0041). In the
    caller's transaction, the one that records the sale. Returns how many deposits were told."""
    if not bag_ids:
        return 0
    rows = (
        await db.execute(
            select(DepositSession, Container.name)
            .join(
                CollectionFill,
                and_(
                    CollectionFill.collection_id == DepositSession.collection_id,
                    CollectionFill.material == DepositSession.declared_material,
                ),
            )
            .join(Container, Container.id == DepositSession.container_id)
            .where(
                CollectionFill.bag_id.in_(bag_ids),
                DepositSession.state.in_(CREDITED_STATES),
                DepositSession.deposited_g > 0,
            )
            .distinct()
        )
    ).all()
    for s, container_name in rows:
        material = MATERIAL_NAMES.get(s.declared_material, s.declared_material)
        await enqueue(
            db,
            resident_id=s.resident_id,
            kind="deposit_sold",
            dedupe_key=f"deposit_sold:{s.id}",
            title=f"Se vendió tu material a {buyer}"[:120],
            body=(
                f"{weight(s.deposited_g)} de {material} que dejaste en {container_name}. "
                "Cuando llegue el pago de la venta, te liquidamos tu parte."
            ),
            data={"url": "/history", "session_id": str(s.id)},
            now=now,
        )
    return len(rows)

"""Operator endpoints for sales, the bank match and hosts' payout addresses (docs/adr/0013)."""

import hashlib
import json
import uuid
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import any_, select, update

from .auth import utcnow
from .collection import parse_bag
from .deps import Operator
from .errors import Invalid
from .models import Bag, CollectionCenter, Host, Incident, Sale, SaleLine, Settlement
from .setup_routes import host_view

router = APIRouter(prefix="/v1/operator", tags=["sales"])

# The buyer's weight must match the bag's within the larger of these (docs/adr/0013).
BAG_TOLERANCE_G = 100
BAG_TOLERANCE_RATIO = 0.05


def bag_tolerance(grams: int) -> int:
    return max(BAG_TOLERANCE_G, round(grams * BAG_TOLERANCE_RATIO))


class LineIn(BaseModel):
    bag: str = Field(max_length=200, description="the bag's QR or code")
    buyer_g: int = Field(gt=0, le=1_000_000, description="the buyer's weight, in grams")
    amount_cop: int = Field(gt=0, le=100_000_000)


class SaleIn(BaseModel):
    buyer: str = Field(min_length=1, max_length=200)
    # The center on record that bought, when it is one (docs/adr/0037).
    center_id: uuid.UUID | None = None
    ticket_ref: str = Field(min_length=1, max_length=100)
    sold_on: date
    lines: list[LineIn] = Field(min_length=1, max_length=100)


class ConfirmIn(BaseModel):
    bank_ref: str = Field(min_length=1, max_length=100)
    received_cop: int = Field(gt=0)


class HostPatch(BaseModel):
    payout_address: str | None = Field(default=None, pattern=r"^0x[0-9a-fA-F]{40}$")

    @field_validator("payout_address")
    @classmethod
    def _lower(cls, v: str | None) -> str | None:
        return v.lower() if v else None


def evidence_hash(body: SaleIn, codes: list[str]) -> str:
    """sha256 of the ticket's canonical JSON: what each on-chain sale carries as evidence."""
    ticket = {
        "buyer": body.buyer,
        "ticket_ref": body.ticket_ref,
        "sold_on": body.sold_on.isoformat(),
        "lines": [
            {"bag": code, "buyer_g": line.buyer_g, "amount_cop": line.amount_cop}
            for code, line in zip(codes, body.lines, strict=True)
        ],
    }
    canonical = json.dumps(ticket, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + hashlib.sha256(canonical).hexdigest()


async def sale_view(db, sale: Sale) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(SaleLine, Bag)
            .join(Bag, Bag.id == SaleLine.bag_id)
            .where(SaleLine.sale_id == sale.id)
            .order_by(SaleLine.created_at, Bag.code)
        )
    ).all()
    return {
        "id": str(sale.id),
        "buyer": sale.buyer,
        "center_id": str(sale.center_id) if sale.center_id else None,
        "ticket_ref": sale.ticket_ref,
        "sold_on": sale.sold_on.date().isoformat(),
        "total_cop": sale.total_cop,
        "evidence_hash": sale.evidence_hash,
        "status": sale.status,
        "recorded_by": sale.recorded_by,
        "bank_ref": sale.bank_ref,
        "confirmed_by": sale.confirmed_by,
        "confirmed_at": sale.confirmed_at.isoformat() if sale.confirmed_at else None,
        "created_at": sale.created_at.isoformat(),
        "lines": [
            {
                "id": str(line.id),
                "bag_code": bag.code,
                "material": bag.material,
                "bag_g": bag.grams,
                "buyer_g": line.buyer_g,
                "amount_cop": line.amount_cop,
                "status": line.status,
                "reason": line.reason,
                "residents_cop": line.residents_cop,
                "collector_cop": line.collector_cop,
                "host_cop": line.host_cop,
                "report_hash": line.report_hash,
                "txs": line.txs,
                "settled_at": line.settled_at.isoformat() if line.settled_at else None,
            }
            for line, bag in rows
        ],
    }


@router.post("/sales", status_code=201)
async def record_sale(body: SaleIn, operator: Operator, request: Request) -> dict[str, Any]:
    """Record a buyer's ticket. Each bag must be sealed and free of open incidents. Nothing goes on
    chain until the bank match is confirmed."""
    try:
        codes = [parse_bag(line.bag) for line in body.lines]
    except Invalid as e:
        raise HTTPException(422, {"code": e.code, "detail": e.detail}) from None
    if len(set(codes)) != len(codes):
        raise HTTPException(422, {"code": "invalid", "detail": "a bag appears twice"})
    tz = ZoneInfo(request.app.state.settings.timezone)
    now = utcnow()
    async with request.app.state.maker() as db:
        bags = {
            b.code: b
            for b in await db.scalars(select(Bag).where(Bag.code.in_(codes)).with_for_update())
        }
        for code in codes:
            bag = bags.get(code)
            if bag is None:
                raise HTTPException(404, {"code": "not_found", "detail": f"unknown bag {code}"})
            if bag.status != "sealed":
                raise HTTPException(
                    409, {"code": "conflict", "detail": f"bag {code} is {bag.status}, not sealed"}
                )
            blocked = await db.scalar(
                select(Incident.id).where(
                    Incident.status == "open", any_(Incident.bag_ids) == bag.id
                )
            )
            if blocked is not None:
                raise HTTPException(
                    409,
                    {"code": "conflict", "detail": f"bag {code} has an open incident to resolve"},
                )
        if body.center_id is not None:
            center = await db.get(CollectionCenter, body.center_id)
            if center is None or not center.active:
                raise HTTPException(
                    404, {"code": "not_found", "detail": "unknown or inactive collection center"}
                )
        sale = Sale(
            id=uuid.uuid4(),
            buyer=body.buyer,
            center_id=body.center_id,
            ticket_ref=body.ticket_ref,
            sold_on=datetime.combine(body.sold_on, time(12), tzinfo=tz),
            total_cop=sum(line.amount_cop for line in body.lines),
            evidence_hash=evidence_hash(body, codes),
            status="recorded",
            recorded_by=operator,
            created_at=now,
        )
        db.add(sale)
        await db.flush()
        for code, line in zip(codes, body.lines, strict=True):
            bag = bags[code]
            bag.status = "sold"
            row = SaleLine(
                id=uuid.uuid4(),
                sale_id=sale.id,
                bag_id=bag.id,
                buyer_g=line.buyer_g,
                amount_cop=line.amount_cop,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            if abs(line.buyer_g - bag.grams) > bag_tolerance(bag.grams):
                db.add(
                    Incident(
                        id=uuid.uuid4(),
                        kind="bag_balance",
                        status="open",
                        bag_ids=[bag.id],
                        expected_g=bag.grams,
                        measured_g=line.buyer_g,
                        detail={
                            "tolerance_g": bag_tolerance(bag.grams),
                            "sale_id": str(sale.id),
                            "bag_code": code,
                        },
                        created_at=now,
                    )
                )
        await db.commit()
        return await sale_view(db, sale)


@router.post("/sales/{sale_id}/confirm")
async def confirm_sale(
    sale_id: uuid.UUID, body: ConfirmIn, operator: Operator, request: Request
) -> dict[str, Any]:
    """The pesos reached the bank: from now on the sale is settled on chain, bag by bag."""
    async with request.app.state.maker() as db:
        sale = await db.get(Sale, sale_id, with_for_update=True)
        if sale is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown sale"})
        if sale.status == "confirmed":
            return await sale_view(db, sale)
        if body.received_cop != sale.total_cop:
            raise HTTPException(
                422,
                {
                    "code": "amount_mismatch",
                    "detail": f"the bank received {body.received_cop} but the ticket says "
                    f"{sale.total_cop}; correct the sale first",
                },
            )
        sale.status, sale.bank_ref = "confirmed", body.bank_ref
        sale.confirmed_by, sale.confirmed_at = operator, utcnow()
        await db.commit()
        return await sale_view(db, sale)


@router.get("/sales")
async def list_sales(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        sales = list(await db.scalars(select(Sale).order_by(Sale.created_at.desc()).limit(100)))
        return [await sale_view(db, s) for s in sales]


@router.get("/sales/{sale_id}")
async def get_sale(sale_id: uuid.UUID, _: Operator, request: Request) -> dict[str, Any]:
    """The sale with its settlement report: what every deposit, the collector and each host got."""
    async with request.app.state.maker() as db:
        sale = await db.get(Sale, sale_id)
        if sale is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown sale"})
        view = await sale_view(db, sale)
        rows = await db.scalars(
            select(Settlement)
            .join(SaleLine, SaleLine.id == Settlement.line_id)
            .where(SaleLine.sale_id == sale_id)
            .order_by(Settlement.party, Settlement.party_ref)
        )
        by_line: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_line.setdefault(str(r.line_id), []).append(
                {
                    "party": r.party,
                    "ref": r.party_ref,
                    "address": r.address,
                    "grams": r.grams,
                    "share_cop": r.share_cop,
                    "paid_cop": r.paid_cop,
                    "tx_hash": r.tx_hash,
                }
            )
        for line in view["lines"]:
            line["settlements"] = by_line.get(line["id"], [])
        return view


@router.get("/hosts")
async def list_hosts(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        return [host_view(h) for h in await db.scalars(select(Host).order_by(Host.name))]


@router.patch("/hosts/{host_id}")
async def update_host(
    host_id: uuid.UUID, body: HostPatch, _: Operator, request: Request
) -> dict[str, Any]:
    """Set where the host's share of each sale is paid. Parts waiting for it are paid next."""
    async with request.app.state.maker() as db:
        host = await db.get(Host, host_id, with_for_update=True)
        if host is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown host"})
        host.payout_address = body.payout_address
        if host.payout_address:
            await db.execute(
                update(SaleLine)
                .where(SaleLine.status == "waiting")
                .values(next_attempt_at=utcnow())
            )
        await db.commit()
        return host_view(host)

"""Operator routes for bank statements: upload, proposals, one-click matches (docs/adr/0039)."""

import base64
import binascii
import hashlib
import uuid
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .bank import BankRow, StatementUnreadable, parse_statement, propose
from .deps import Operator
from .errors import SessionError
from .models import BankLine, BankStatement, Merchant, RedemptionRequest, Sale
from .payment_routes import _operator_key
from .sale_routes import apply_bank_match
from .sessions import utcnow

router = APIRouter(prefix="/v1/operator", tags=["bank statements"])
MAX_FILE_BYTES = 5 * 1024 * 1024


class StatementIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1, max_length=8_000_000)


class MatchIn(BaseModel):
    kind: Literal["sale", "redemption"]
    target_id: uuid.UUID


def line_view(line: BankLine) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "posted_on": line.posted_on.isoformat(),
        "description": line.description,
        "reference": line.reference,
        "amount_cop": line.amount_cop,
        "matched_kind": line.matched_kind,
        "matched_id": str(line.matched_id) if line.matched_id else None,
        "matched_by": line.matched_by,
    }


async def proposals(db, tz: ZoneInfo) -> list[dict[str, Any]]:
    lines = list(await db.scalars(select(BankLine).where(BankLine.matched_id.is_(None))))
    sales = list(await db.scalars(select(Sale).where(Sale.status == "recorded")))
    pending = list(
        await db.execute(
            select(RedemptionRequest, Merchant)
            .join(Merchant, Merchant.resident_id == RedemptionRequest.merchant_id)
            .where(RedemptionRequest.status == "pending")
        )
    )
    found = propose(
        [
            {
                "id": line.id,
                "posted_on": line.posted_on,
                "description": line.description,
                "reference": line.reference,
                "amount_cop": line.amount_cop,
            }
            for line in lines
        ],
        [
            {
                "id": s.id,
                "total_cop": s.total_cop,
                "sold_on": s.sold_on.astimezone(tz).date(),
                "ticket_ref": s.ticket_ref,
                "buyer": s.buyer,
            }
            for s in sales
        ],
        [
            {
                "id": r.id,
                "amount_cop": r.amount_cop,
                "requested_on": r.created_at.astimezone(tz).date(),
                "merchant": m.name,
                "tax_id": m.nit,
            }
            for r, m in pending
        ],
    )
    by_line = {str(line.id): line for line in lines}
    sale_by_id = {str(s.id): s for s in sales}
    red_by_id = {str(r.id): (r, m) for r, m in pending}
    out = []
    for p in found:
        if p.kind == "sale":
            s = sale_by_id[p.target_id]
            target = {"ticket_ref": s.ticket_ref, "buyer": s.buyer, "amount_cop": s.total_cop}
        else:
            r, m = red_by_id[p.target_id]
            target = {"merchant": m.name, "nit": m.nit, "amount_cop": r.amount_cop}
        out.append(
            {
                "line": line_view(by_line[p.line_id]),
                "kind": p.kind,
                "target_id": p.target_id,
                "target": target,
                "score": p.score,
                "why": p.why,
            }
        )
    return out


@router.post("/bank-statements", status_code=201)
async def upload_statement(body: StatementIn, who: Operator, request: Request) -> dict[str, Any]:
    try:
        content = base64.b64decode(body.content_base64, validate=True)
    except binascii.Error:
        raise HTTPException(422, {"code": "invalid", "detail": "the file is not base64"}) from None
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, {"code": "invalid", "detail": "the file is over 5 MB"})
    try:
        rows = parse_statement(body.filename, content)
    except StatementUnreadable as e:
        raise HTTPException(422, {"code": "unreadable", "detail": str(e)}) from None
    tz = ZoneInfo(request.app.state.settings.timezone)
    async with request.app.state.maker() as db:
        statement = BankStatement(
            id=uuid.uuid4(),
            filename=body.filename,
            file_sha256=hashlib.sha256(content).hexdigest(),
            lines=len(rows),
            uploaded_by=who,
        )
        db.add(statement)
        seen: dict[tuple, int] = {}
        prints = []
        for row in rows:
            key = (row.posted_on, row.amount_cop, row.reference, row.description)
            seen[key] = seen.get(key, -1) + 1
            prints.append((row, row.fingerprint(seen[key])))
        existing = set(
            await db.scalars(
                select(BankLine.fingerprint).where(BankLine.fingerprint.in_([f for _, f in prints]))
            )
        )
        added = 0
        for row, fingerprint in prints:
            if fingerprint in existing:
                continue
            db.add(_line(statement.id, row, fingerprint))
            added += 1
        await db.commit()
        return {
            "statement_id": str(statement.id),
            "movements": len(rows),
            "added": added,
            "already_known": len(rows) - added,
            "proposals": await proposals(db, tz),
        }


def _line(statement_id: uuid.UUID, row: BankRow, fingerprint: str) -> BankLine:
    return BankLine(
        id=uuid.uuid4(),
        statement_id=statement_id,
        posted_on=row.posted_on,
        description=row.description,
        reference=row.reference,
        amount_cop=row.amount_cop,
        fingerprint=fingerprint,
    )


@router.get("/bank-proposals")
async def list_proposals(_: Operator, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        return await proposals(db, ZoneInfo(request.app.state.settings.timezone))


@router.post("/bank-lines/{line_id}/match")
async def match_line(
    line_id: uuid.UUID, body: MatchIn, who: Operator, request: Request
) -> dict[str, Any]:
    """Confirm that this movement pays that sale or redemption: the same as confirming it by hand
    with the movement's reference."""
    async with request.app.state.maker() as db:
        line = await db.get(BankLine, line_id, with_for_update=True)
        if line is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown bank line"})
        if line.matched_id is not None:
            raise HTTPException(409, {"code": "conflict", "detail": "this movement is matched"})
        bank_ref = (line.reference or line.description or str(line.id))[:100]
        if body.kind == "sale":
            sale = await db.get(Sale, body.target_id, with_for_update=True)
            if sale is None:
                raise HTTPException(404, {"code": "not_found", "detail": "unknown sale"})
            if line.amount_cop <= 0:
                raise HTTPException(
                    422, {"code": "invalid", "detail": "a sale is paid by a credit"}
                )
            apply_bank_match(sale, bank_ref, line.amount_cop, who)
        else:
            if line.amount_cop >= 0:
                raise HTTPException(
                    422, {"code": "invalid", "detail": "a redemption is paid by a debit"}
                )
            r = await db.get(RedemptionRequest, body.target_id)
            if r is None or r.amount_cop != -line.amount_cop:
                raise HTTPException(
                    422, {"code": "amount_mismatch", "detail": "the amounts do not match"}
                )
            try:
                await request.app.state.payments.decide_redemption(
                    body.target_id, True, bank_ref, who, _operator_key(request)
                )
            except SessionError as e:
                raise HTTPException(e.status, {"code": e.code, "detail": e.detail}) from None
        line.matched_kind, line.matched_id = body.kind, body.target_id
        line.matched_by, line.matched_at = who, utcnow()
        await db.commit()
        return line_view(line)

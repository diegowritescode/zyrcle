"""Operator routes for reading scale tickets with AI (docs/adr/0038)."""

import base64
import binascii
import hashlib
import uuid
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .deps import Operator
from .models import Bag, CollectionCenter, TicketScan
from .tickets import TicketRead, TicketUnreadable, checks, propose_bags

router = APIRouter(prefix="/v1/operator", tags=["ticket scans"])
MAX_IMAGE_BYTES = 5 * 1024 * 1024


class ScanIn(BaseModel):
    image_base64: str = Field(min_length=1, max_length=8_000_000)
    media_type: Literal["image/jpeg", "image/png", "image/webp"]


async def scan_view(db, scan: TicketScan) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(scan.id),
        "status": scan.status,
        "reading": scan.reading,
        "error": scan.error,
        "model": scan.model,
        "created_by": scan.created_by,
        "created_at": scan.created_at.isoformat(),
        "sale_id": str(scan.sale_id) if scan.sale_id else None,
        "checks": [],
        "proposed_bags": [],
        "center_id": None,
    }
    if scan.reading is None:
        return view
    read = TicketRead.model_validate(scan.reading)
    bags = await db.scalars(select(Bag).where(Bag.status == "sealed").order_by(Bag.created_at))
    sealed = [{"code": b.code, "material": b.material, "grams": b.grams or 0} for b in bags]
    view["checks"] = checks(read)
    view["proposed_bags"] = propose_bags(read, sealed)
    if read.center_name:
        center = await db.scalar(
            select(CollectionCenter).where(
                func.lower(CollectionCenter.name).contains(read.center_name.lower().strip())
            )
        )
        view["center_id"] = str(center.id) if center else None
    return view


@router.post("/ticket-scans", status_code=201)
async def scan_ticket(body: ScanIn, who: Operator, request: Request) -> dict[str, Any]:
    reader = request.app.state.ticket_reader
    if reader is None:
        raise HTTPException(
            503, {"code": "unavailable", "detail": "ticket reading is off (no Anthropic key)"}
        )
    try:
        image = base64.b64decode(body.image_base64, validate=True)
    except binascii.Error:
        raise HTTPException(422, {"code": "invalid", "detail": "the image is not base64"}) from None
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(413, {"code": "invalid", "detail": "the image is over 5 MB"})
    scan = TicketScan(
        id=uuid.uuid4(),
        image=image,
        media_type=body.media_type,
        image_sha256=hashlib.sha256(image).hexdigest(),
        created_by=who,
    )
    try:
        reading = await reader.read(body.image_base64, body.media_type)
        scan.status, scan.reading = "read", reading.read.model_dump()
        scan.model, scan.request_id = reading.model, reading.request_id
    except TicketUnreadable as e:
        scan.status, scan.error = "failed", str(e)
    except Exception as e:  # the API is down, the key is wrong: say so, keep the photo
        scan.status, scan.error = "failed", f"{type(e).__name__}: {e}"
    async with request.app.state.maker() as db:
        db.add(scan)
        await db.commit()
        return await scan_view(db, scan)


@router.get("/ticket-scans/{scan_id}")
async def get_scan(scan_id: uuid.UUID, _: Operator, request: Request) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        scan = await db.get(TicketScan, scan_id)
        if scan is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown ticket scan"})
        return await scan_view(db, scan)


@router.get("/ticket-scans/{scan_id}/image")
async def scan_image(scan_id: uuid.UUID, _: Operator, request: Request) -> Response:
    async with request.app.state.maker() as db:
        scan = await db.get(TicketScan, scan_id)
        if scan is None:
            raise HTTPException(404, {"code": "not_found", "detail": "unknown ticket scan"})
        return Response(scan.image, media_type=scan.media_type)

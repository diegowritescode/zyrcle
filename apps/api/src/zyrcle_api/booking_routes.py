"""Resident endpoints for time slots: a container's hours, booking one, cancelling it."""

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field

from . import bookings
from .api import Resident
from .auth import utcnow
from .errors import SessionError
from .models import Container, Residence

router = APIRouter(prefix="/v1", tags=["bookings"])


def _tz(request: Request) -> ZoneInfo:
    return ZoneInfo(request.app.state.settings.timezone)


def _http(e: SessionError) -> HTTPException:
    return HTTPException(e.status, {"code": e.code, "detail": e.detail})


class BookingIn(BaseModel):
    container_id: str = Field(max_length=64)
    starts_at: AwareDatetime


@router.get("/containers/{container_id}/slots")
async def container_slots(
    container_id: str, resident: Resident, request: Request, day: date | None = None
) -> dict[str, Any]:
    async with request.app.state.maker() as db:
        try:
            return await bookings.slots(db, resident, container_id, day, utcnow(), _tz(request))
        except SessionError as e:
            raise _http(e) from None


@router.get("/bookings")
async def my_bookings(resident: Resident, request: Request) -> list[dict[str, Any]]:
    async with request.app.state.maker() as db:
        return await bookings.upcoming(db, resident, utcnow(), _tz(request))


@router.post("/bookings", status_code=201)
async def create_booking(body: BookingIn, resident: Resident, request: Request) -> dict[str, Any]:
    now, tz = utcnow(), _tz(request)
    async with request.app.state.maker() as db:
        try:
            b = await bookings.book(db, resident, body.container_id, body.starts_at, now, tz)
        except SessionError as e:
            raise _http(e) from None
        await db.commit()
        return await _view(db, b, now, tz)


@router.delete("/bookings/{booking_id}")
async def cancel_booking(
    booking_id: uuid.UUID, resident: Resident, request: Request
) -> dict[str, Any]:
    now, tz = utcnow(), _tz(request)
    async with request.app.state.maker() as db:
        try:
            b = await bookings.cancel(db, resident, booking_id, now)
        except SessionError as e:
            raise _http(e) from None
        await db.commit()
        return await _view(db, b, now, tz)


async def _view(db, b, now: datetime, tz: ZoneInfo) -> dict[str, Any]:
    container = await db.get(Container, b.container_id)
    residence = await db.get(Residence, container.residence_id)
    return bookings.booking_view(b, container, residence, now, tz)

"""Time-slot bookings (docs/adr/0009-time-slots.md).

Every function runs inside the caller's transaction. Counting the spots of an hour and taking one
happen under a lock on the container row, so two residents can never take the last spot together.
"""

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .domain.slots import (
    MAX_UPCOMING,
    SLOT,
    Hours,
    bookable_days,
    day_slots,
    is_slot_start,
    slot_start,
    slot_state,
)
from .errors import (
    AlreadyBooked,
    Closed,
    Conflict,
    Forbidden,
    Invalid,
    NotFound,
    RecoveryPending,
    SlotFull,
    TooManyBookings,
)
from .models import Booking, Container, Site
from .recovery import recovery_pending


def hours_of(site: Site) -> Hours:
    return Hours(site.opens_hour, site.closes_hour)


async def _locked_container(db: AsyncSession, container_id: str) -> tuple[Container, Site]:
    container = await db.get(Container, container_id, with_for_update=True)
    if container is None:
        raise NotFound("unknown container")
    site = await db.get(Site, container.site_id)
    assert site is not None
    return container, site


async def _taken(db: AsyncSession, container_id: str, starts_at: datetime) -> int:
    return (
        await db.scalar(
            select(func.count(Booking.id)).where(
                Booking.container_id == container_id,
                Booking.starts_at == starts_at,
                Booking.status == "booked",
            )
        )
        or 0
    )


async def _mine(
    db: AsyncSession, resident_id: uuid.UUID, container_id: str, starts_at: datetime
) -> Booking | None:
    return await db.scalar(
        select(Booking).where(
            Booking.resident_id == resident_id,
            Booking.container_id == container_id,
            Booking.starts_at == starts_at,
            Booking.status == "booked",
        )
    )


async def claim_spot(
    db: AsyncSession,
    resident_id: uuid.UUID,
    container: Container,
    now: datetime,
    tz: ZoneInfo,
) -> Booking:
    """The spot a resident uses to open a container now: their booking for this hour, or a
    walk-in spot if the hour still has room. The caller must hold the container row lock."""
    site = await db.get(Site, container.site_id)
    assert site is not None
    start = slot_start(now, tz)
    hours = hours_of(site)
    if not hours.contains(start.hour):
        raise Closed(f"the container is open from {hours.label()}")
    booking = await _mine(db, resident_id, container.id, start)
    if booking is not None:
        if booking.used_at is None:
            booking.used_at, booking.updated_at = now, now
        return booking
    if await _taken(db, container.id, start) >= site.slot_capacity:
        raise SlotFull("every spot of this hour is booked")
    booking = Booking(
        id=uuid.uuid4(),
        resident_id=resident_id,
        container_id=container.id,
        starts_at=start,
        status="booked",
        walk_in=True,
        used_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(booking)
    return booking


async def book(
    db: AsyncSession,
    resident_id: uuid.UUID,
    container_id: str,
    starts_at: datetime,
    now: datetime,
    tz: ZoneInfo,
) -> Booking:
    if starts_at.tzinfo is None:
        raise Invalid("starts_at needs a time zone offset")
    if await recovery_pending(db, resident_id):
        raise RecoveryPending("this phone is waiting to recover an account")
    container, site = await _locked_container(db, container_id)
    if not is_slot_start(starts_at, tz):
        raise Invalid("a slot starts on the hour")
    start = starts_at.astimezone(tz)
    if slot_state(start, now) == "past":
        raise Invalid("that hour is over")
    if start.date() not in bookable_days(now, tz):
        raise Invalid("bookings open up to 7 days ahead")
    hours = hours_of(site)
    if not hours.contains(start.hour):
        raise Closed(f"the container is open from {hours.label()}")
    if await _mine(db, resident_id, container_id, start) is not None:
        raise AlreadyBooked("you already have this hour")
    upcoming = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.resident_id == resident_id,
            Booking.status == "booked",
            Booking.walk_in.is_(False),
            Booking.used_at.is_(None),
            Booking.starts_at > now - SLOT,
        )
    )
    if (upcoming or 0) >= MAX_UPCOMING:
        raise TooManyBookings(f"you can hold up to {MAX_UPCOMING} upcoming bookings")
    if await _taken(db, container_id, start) >= site.slot_capacity:
        raise SlotFull("every spot of this hour is booked")
    booking = Booking(
        id=uuid.uuid4(),
        resident_id=resident_id,
        container_id=container_id,
        starts_at=start,
        status="booked",
        walk_in=False,
        created_at=now,
        updated_at=now,
    )
    db.add(booking)
    return booking


async def cancel(
    db: AsyncSession, resident_id: uuid.UUID, booking_id: uuid.UUID, now: datetime
) -> Booking:
    booking = await db.get(Booking, booking_id, with_for_update=True)
    if booking is None or booking.resident_id != resident_id:
        raise NotFound("unknown booking")
    if booking.status == "cancelled":
        return booking
    if booking.walk_in or booking.used_at is not None:
        raise Forbidden("this spot was already used")
    if slot_state(booking.starts_at, now) == "past":
        raise Conflict("that hour is over")
    booking.status, booking.updated_at = "cancelled", now
    return booking


def booking_view(
    b: Booking, container: Container, site: Site, now: datetime, tz: ZoneInfo
) -> dict[str, Any]:
    start = b.starts_at.astimezone(tz)
    when = slot_state(start, now)
    if b.status == "cancelled":
        state = "cancelled"
    elif b.used_at is not None:
        state = "used"
    else:
        state = {"past": "missed", "now": "now", "future": "upcoming"}[when]
    return {
        "id": str(b.id),
        "container_id": container.id,
        "container_name": container.name,
        "site_name": site.name,
        "starts_at": start.isoformat(),
        "ends_at": (start + SLOT).isoformat(),
        "day": start.date().isoformat(),
        "hour": start.hour,
        "state": state,
        "walk_in": b.walk_in,
    }


async def upcoming(
    db: AsyncSession, resident_id: uuid.UUID, now: datetime, tz: ZoneInfo
) -> list[dict[str, Any]]:
    """The resident's booked hours that have not ended, soonest first (walk-ins excluded)."""
    rows = await db.execute(
        select(Booking, Container, Site)
        .join(Container, Container.id == Booking.container_id)
        .join(Site, Site.id == Container.site_id)
        .where(
            Booking.resident_id == resident_id,
            Booking.status == "booked",
            Booking.walk_in.is_(False),
            Booking.starts_at > now - SLOT,
        )
        .order_by(Booking.starts_at)
    )
    return [booking_view(b, c, r, now, tz) for b, c, r in rows]


async def slots(
    db: AsyncSession,
    resident_id: uuid.UUID,
    container_id: str,
    day: date | None,
    now: datetime,
    tz: ZoneInfo,
) -> dict[str, Any]:
    """One day of a container's hours: how many spots are taken and which one is the resident's."""
    container = await db.get(Container, container_id)
    if container is None:
        raise NotFound("unknown container")
    site = await db.get(Site, container.site_id)
    assert site is not None
    days = bookable_days(now, tz)
    day = day or days[0]
    if day not in days:
        raise Invalid("bookings open up to 7 days ahead")
    hours = hours_of(site)
    starts = day_slots(day, hours, tz)
    first, last = (starts[0], starts[-1] + SLOT) if starts else (now, now)
    in_day = (
        Booking.container_id == container_id,
        Booking.status == "booked",
        Booking.starts_at >= first,
        Booking.starts_at < last,
    )
    taken = {
        at: n
        for at, n in await db.execute(
            select(Booking.starts_at, func.count(Booking.id))
            .where(*in_day)
            .group_by(Booking.starts_at)
        )
    }
    mine = set(
        await db.scalars(
            select(Booking.starts_at).where(*in_day, Booking.resident_id == resident_id)
        )
    )
    out = []
    for start in starts:
        n = taken.get(start, 0)
        when = slot_state(start, now)
        out.append(
            {
                "starts_at": start.isoformat(),
                "ends_at": (start + SLOT).isoformat(),
                "hour": start.hour,
                "taken": n,
                "capacity": site.slot_capacity,
                "mine": start in mine,
                "state": when,
                "available": when != "past" and n < site.slot_capacity and start not in mine,
            }
        )
    return {
        "container_id": container.id,
        "container_name": container.name,
        "site_name": site.name,
        "timezone": str(tz),
        "opens_hour": site.opens_hour,
        "closes_hour": site.closes_hour,
        "capacity": site.slot_capacity,
        "days": [d.isoformat() for d in days],
        "day": day.isoformat(),
        "slots": out,
    }


def site_schedule(site: Site) -> dict[str, Any]:
    return {
        "id": str(site.id),
        "host_id": str(site.host_id),
        "name": site.name,
        "opens_hour": site.opens_hour,
        "closes_hour": site.closes_hour,
        "slot_capacity": site.slot_capacity,
    }

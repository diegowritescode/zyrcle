"""Hourly time slots (docs/adr/0009-time-slots.md). Pure: no I/O.

Slots are whole local hours in the deployment's time zone. A site is open over
[opens_hour, closes_hour); each container takes `slot_capacity` residents per hour.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SLOT = timedelta(hours=1)
# How far ahead a resident can book, counting today.
HORIZON_DAYS = 7
# Booked (not walk-in) spots a resident can hold at once.
MAX_UPCOMING = 3


@dataclass(frozen=True)
class Hours:
    opens: int
    closes: int

    def contains(self, local_hour: int) -> bool:
        return self.opens <= local_hour < self.closes

    def label(self) -> str:
        return f"{self.opens:02d}:00 to {self.closes:02d}:00"


def slot_start(at: datetime, tz: ZoneInfo) -> datetime:
    """The start of the local hour that contains `at`."""
    return at.astimezone(tz).replace(minute=0, second=0, microsecond=0)


def is_slot_start(at: datetime, tz: ZoneInfo) -> bool:
    local = at.astimezone(tz)
    return local.minute == 0 and local.second == 0 and local.microsecond == 0


def bookable_days(now: datetime, tz: ZoneInfo) -> list[date]:
    today = now.astimezone(tz).date()
    return [today + timedelta(days=i) for i in range(HORIZON_DAYS)]


def day_slots(day: date, hours: Hours, tz: ZoneInfo) -> list[datetime]:
    return [datetime.combine(day, time(h), tzinfo=tz) for h in range(hours.opens, hours.closes)]


def slot_state(starts_at: datetime, now: datetime) -> str:
    """ "past" once the hour ended, "now" during it, "future" before it."""
    if starts_at + SLOT <= now:
        return "past"
    return "now" if starts_at <= now else "future"

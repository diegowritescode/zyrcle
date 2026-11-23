"""Hosts, sites, devices and the containers on them (docs/adr/0011)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now

HOST_KINDS = ("university", "residential", "business", "public")


class Host(Base):
    """The institution that lets Zyrcle put containers on its sites (docs/adr/0011): a university,
    a residential complex, a business. It is a party to the money and to the impact reports."""

    __tablename__ = "host"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in HOST_KINDS) + ")", name="host_kind_valid"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))
    # Where the host's share of each sale is paid (docs/adr/0013). None: not paid yet.
    payout_address: Mapped[str | None] = mapped_column(String(42))
    created_at: Mapped[datetime] = _now()


class Site(Base):
    """A place a host runs, with its own containers, opening hours and turns: a campus, a building,
    a residential complex. It was called a residence before docs/adr/0011."""

    __tablename__ = "site"
    __table_args__ = (
        CheckConstraint(
            "0 <= opens_hour AND opens_hour < closes_hour AND closes_hour <= 24",
            name="site_hours_valid",
        ),
        CheckConstraint("slot_capacity > 0", name="site_slot_capacity_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("host.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # Opening hours in local time (settings.timezone), as whole hours: [opens_hour, closes_hour).
    opens_hour: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    closes_hour: Mapped[int] = mapped_column(SmallInteger, default=24, server_default=text("24"))
    # Participants per container per hour (docs/adr/0009-time-slots.md).
    slot_capacity: Mapped[int] = mapped_column(SmallInteger, default=20, server_default=text("20"))
    created_at: Mapped[datetime] = _now()


class Device(Base):
    __tablename__ = "device"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    public_key_pem: Mapped[str] = mapped_column(Text)
    last_seq: Mapped[int] = mapped_column(BigInteger, server_default=text("-1"))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    firmware: Mapped[str | None] = mapped_column(String(64))
    current_code: Mapped[str | None] = mapped_column(String(16))
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The code shown before the last rotation stays valid until it expires, so a resident who
    # scanned it a second before the screen changed is not rejected.
    previous_code: Mapped[str | None] = mapped_column(String(16))
    previous_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class Container(Base):
    __tablename__ = "container"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("site.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("device.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    accepted_materials: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    area_mm2: Mapped[int] = mapped_column(
        Integer, CheckConstraint("area_mm2 > 0", name="container_area_mm2_check")
    )
    depth_mm: Mapped[int] = mapped_column(
        Integer, CheckConstraint("depth_mm > 0", name="container_depth_mm_check")
    )
    created_at: Mapped[datetime] = _now()

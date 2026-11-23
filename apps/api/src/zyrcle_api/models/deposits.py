"""Deposits, their events, raw device messages, and bookings."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import ACTIVE_SQL, STATES_SQL, Base, _now


class DepositSession(Base):
    __tablename__ = "deposit_session"
    __table_args__ = (
        CheckConstraint(f"state IN ({STATES_SQL})", name="deposit_session_state_valid"),
        # One active session per container, enforced by the database even under concurrent requests.
        Index(
            "one_active_session_per_container",
            "container_id",
            unique=True,
            postgresql_where=text(f"state IN ({ACTIVE_SQL})"),
        ),
        Index("deposit_session_state_idx", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    container_id: Mapped[str] = mapped_column(ForeignKey("container.id"))
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"))
    state: Mapped[str] = mapped_column(String(16))
    declared_material: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    last_activity_at: Mapped[datetime] = _now()
    close_reason: Mapped[str | None] = mapped_column(String(32))

    tare_g: Mapped[int | None] = mapped_column(Integer)
    last_weight_g: Mapped[int | None] = mapped_column(Integer)
    final_g: Mapped[int | None] = mapped_column(Integer)
    fill_before_mm: Mapped[int | None] = mapped_column(Integer)
    fill_after_mm: Mapped[int | None] = mapped_column(Integer)
    metal_detected: Mapped[bool | None]
    camera_label: Mapped[str | None] = mapped_column(String(32))
    added_volume_ml: Mapped[int | None] = mapped_column(Integer)
    deposited_g: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float | None] = mapped_column(Float)
    reasons: Mapped[list[str] | None] = mapped_column(JSONB)
    reviewed_by: Mapped[str | None] = mapped_column(String(254))
    review_note: Mapped[str | None] = mapped_column(Text)
    # The collection that took this deposit's material out of the container (docs/adr/0012).
    collection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection.id"), index=True)


class SessionEvent(Base):
    """Append-only audit log of everything that happened to a session."""

    __tablename__ = "session_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deposit_session.id"), index=True)
    at: Mapped[datetime] = _now()
    kind: Mapped[str] = mapped_column(String(32))
    from_state: Mapped[str | None] = mapped_column(String(16))
    to_state: Mapped[str | None] = mapped_column(String(16))
    data: Mapped[dict | None] = mapped_column(JSONB)


class DeviceMessage(Base):
    """Every verified device message, keyed by (device, seq): replays and duplicates are no-ops."""

    __tablename__ = "device_message"
    device_id: Mapped[str] = mapped_column(ForeignKey("device.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    device_ts: Mapped[int] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = _now()
    body: Mapped[dict] = mapped_column(JSONB)


class Booking(Base):
    """A resident's spot in one hour of one container (docs/adr/0009-time-slots.md).

    A booked spot is guaranteed. A resident who arrives without one gets a walk-in spot if the hour
    still has room, so `walk_in` rows count against the capacity like any other.
    """

    __tablename__ = "booking"
    __table_args__ = (
        CheckConstraint("status IN ('booked', 'cancelled')", name="booking_status_valid"),
        # One live spot per resident per container and hour, even under concurrent requests.
        Index(
            "one_booking_per_resident_slot",
            "resident_id",
            "container_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status = 'booked'"),
        ),
        Index("booking_slot_idx", "container_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    container_id: Mapped[str] = mapped_column(ForeignKey("container.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # a local hour boundary
    status: Mapped[str] = mapped_column(String(16))
    walk_in: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()

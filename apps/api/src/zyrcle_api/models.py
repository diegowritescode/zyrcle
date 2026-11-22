"""Persistence model. Weights in integer grams, distances in mm, volumes in ml."""

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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .domain.session_machine import ACTIVE, State

ACTIVE_SQL = ", ".join(f"'{s.value}'" for s in sorted(ACTIVE))
STATES_SQL = ", ".join(f"'{s.value}'" for s in State)


class Base(DeclarativeBase):
    pass


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Residence(Base):
    __tablename__ = "residence"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
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
    residence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residence.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("device.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    accepted_materials: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    area_mm2: Mapped[int] = mapped_column(Integer, CheckConstraint("area_mm2 > 0"))
    depth_mm: Mapped[int] = mapped_column(Integer, CheckConstraint("depth_mm > 0"))
    created_at: Mapped[datetime] = _now()


class Resident(Base):
    __tablename__ = "resident"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    address: Mapped[str] = mapped_column(String(42), unique=True)  # lowercase 0x address
    created_at: Mapped[datetime] = _now()


class AuthNonce(Base):
    __tablename__ = "auth_nonce"
    nonce: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    review_note: Mapped[str | None] = mapped_column(Text)


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


class MaterialPrice(Base):
    """Reference price per material, used to size advances. Set by the operator until enough
    confirmed sales exist to compute it from them (docs/architecture.md, section 8)."""

    __tablename__ = "material_price"
    material: Mapped[str] = mapped_column(String(32), primary_key=True)
    cop_per_kg: Mapped[int] = mapped_column(Integer, CheckConstraint("cop_per_kg >= 0"))
    source: Mapped[str] = mapped_column(String(16))  # manual | sales
    updated_at: Mapped[datetime] = _now()


PAYOUT_STATUSES = ("pending", "submitting", "confirmed", "deferred", "failed")


class Payout(Base):
    """Transactional outbox for on-chain payments. Written in the same transaction that credits a
    deposit; a worker turns it into a Treasury call. Exactly one advance per session."""

    __tablename__ = "payout"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in PAYOUT_STATUSES) + ")",
            name="payout_status_valid",
        ),
        CheckConstraint("amount_cop > 0", name="payout_amount_positive"),
        Index("payout_due_idx", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deposit_session.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(16))  # advance (settlements come with sales)
    resident_address: Mapped[str] = mapped_column(String(42))
    amount_cop: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    tx_hash: Mapped[str | None] = mapped_column(String(66))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()

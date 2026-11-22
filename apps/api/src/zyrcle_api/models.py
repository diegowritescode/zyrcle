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
    SmallInteger,
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
    __table_args__ = (
        CheckConstraint(
            "0 <= opens_hour AND opens_hour < closes_hour AND closes_hour <= 24",
            name="residence_hours_valid",
        ),
        CheckConstraint("slot_capacity > 0", name="residence_slot_capacity_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    # Opening hours in local time (settings.timezone), as whole hours: [opens_hour, closes_hour).
    opens_hour: Mapped[int] = mapped_column(SmallInteger, default=0, server_default=text("0"))
    closes_hour: Mapped[int] = mapped_column(SmallInteger, default=24, server_default=text("24"))
    # Residents per container per hour (docs/adr/0009-time-slots.md).
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
    residence_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("residence.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("device.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    accepted_materials: Mapped[list[str]] = mapped_column(ARRAY(String(32)))
    area_mm2: Mapped[int] = mapped_column(Integer, CheckConstraint("area_mm2 > 0"))
    depth_mm: Mapped[int] = mapped_column(Integer, CheckConstraint("depth_mm > 0"))
    created_at: Mapped[datetime] = _now()


class Resident(Base):
    """A resident is their account, not their phone (docs/adr/0010-smart-accounts-and-recovery.md).

    `address` is where their ZYR lives and never changes: their smart account on ZyrcleChain.
    `owner_address` is the phone key that signs in and controls the account; a recovery replaces
    it. Both are lowercase 0x addresses. Residents from before smart accounts have both equal (the
    phone key held the ZYR itself) until they next sign in.
    """

    __tablename__ = "resident"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    address: Mapped[str] = mapped_column(String(42), unique=True)
    owner_address: Mapped[str] = mapped_column(String(42), unique=True)
    # Verified recovery email, lowercase. Set only after the resident typed the code sent to it.
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class PushToken(Base):
    """An Expo push token: one per installed app. Registering it again from another wallet moves
    it there, since only the wallet now on that phone should get its notifications."""

    __tablename__ = "push_token"
    token: Mapped[str] = mapped_column(String(200), primary_key=True)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    # Set when Expo reports the app was uninstalled (DeviceNotRegistered). Re-registering clears it.
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


NOTIFICATION_STATUSES = ("pending", "sent", "skipped", "failed")


class Notification(Base):
    """Outbox for push notifications, written in the transaction that caused them
    (docs/adr/0008-push-notifications.md). `dedupe_key` makes enqueueing idempotent."""

    __tablename__ = "notification"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in NOTIFICATION_STATUSES) + ")",
            name="notification_status_valid",
        ),
        Index("notification_due_idx", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(400))
    data: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Expo push tickets awaiting a receipt: [{"token": ..., "id": ...}].
    tickets: Mapped[list | None] = mapped_column(JSONB)
    receipts_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailCode(Base):
    """A six-digit code sent by email: to verify a recovery email or to recover an account. Only
    an HMAC of the code is stored. Bound to the resident who asked, so a code is useless on
    another phone."""

    __tablename__ = "email_code"
    __table_args__ = (
        CheckConstraint("purpose IN ('verify', 'recover')", name="email_code_purpose_valid"),
        Index("email_code_lookup_idx", "email", "purpose", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(String(16))
    email: Mapped[str] = mapped_column(String(254))
    resident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resident.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


RECOVERY_STATUSES = ("starting", "waiting", "cancelling", "done", "cancelled", "failed")
RECOVERY_LIVE = ("starting", "waiting", "cancelling")
_LIVE_SQL = ", ".join(f"'{s}'" for s in RECOVERY_LIVE)


class AccountRecovery(Base):
    """Handing an account to a new phone key (docs/adr/0010). The new phone signed in as a
    resident of its own (`new_resident_id`), which is folded into the account when it is done.

    starting   -> the guardian must call startRecovery on chain
    waiting    -> on chain; finishRecovery once `ready_at` passes
    cancelling -> the guardian must call cancelRecovery on chain
    done | cancelled | failed
    """

    __tablename__ = "account_recovery"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in RECOVERY_STATUSES) + ")",
            name="account_recovery_status_valid",
        ),
        Index(
            "one_live_recovery_per_account",
            "resident_id",
            unique=True,
            postgresql_where=text(f"status IN ({_LIVE_SQL})"),
        ),
        Index(
            "one_live_recovery_per_new_phone",
            "new_resident_id",
            unique=True,
            postgresql_where=text(f"status IN ({_LIVE_SQL})"),
        ),
        Index("account_recovery_due_idx", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    new_resident_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resident.id", ondelete="SET NULL")
    )
    account_address: Mapped[str] = mapped_column(String(42))
    new_owner: Mapped[str] = mapped_column(String(42))
    status: Mapped[str] = mapped_column(String(16))
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(String(16))  # owner | new_phone | chain
    start_tx: Mapped[str | None] = mapped_column(String(66))
    finish_tx: Mapped[str | None] = mapped_column(String(66))
    cancel_tx: Mapped[str | None] = mapped_column(String(66))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


EMAIL_STATUSES = ("pending", "sent", "failed")


class EmailMessage(Base):
    """Outbox for email, written in the transaction that caused it and sent by a worker through
    Resend. The bodies of code emails are cleared once sent or given up on."""

    __tablename__ = "email_message"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in EMAIL_STATUSES) + ")",
            name="email_message_status_valid",
        ),
        Index("email_message_due_idx", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    to: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    text_body: Mapped[str] = mapped_column(Text)
    html_body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # The version of the data-processing policy the participant accepted, and when (Ley 1581 de
    # 2012, docs/adr/0028). None: not accepted yet.
    privacy_version: Mapped[str | None] = mapped_column(String(16))
    privacy_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class MaterialPrice(Base):
    """Reference price per material, used to size advances. Set by the operator until enough
    confirmed sales exist to compute it from them (docs/architecture.md, section 8)."""

    __tablename__ = "material_price"
    material: Mapped[str] = mapped_column(String(32), primary_key=True)
    cop_per_kg: Mapped[int] = mapped_column(
        Integer, CheckConstraint("cop_per_kg >= 0", name="material_price_cop_per_kg_check")
    )
    source: Mapped[str] = mapped_column(String(16))  # manual (sales: planned, not written yet)
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
    cancelled_by: Mapped[str | None] = mapped_column(String(16))  # owner|new_phone|chain|replaced
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


class Collector(Base):
    """A participant the operator named a collector (docs/adr/0012). Paid at the same account."""

    __tablename__ = "collector"
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = _now()


BAG_STATUSES = ("open", "sealed", "sold", "settled")


class Bag(Base):
    """A bag with a printed QR, holding one material (docs/adr/0012). `grams` is the sum of what
    the containers' scales measured into it."""

    __tablename__ = "bag"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in BAG_STATUSES) + ")",
            name="bag_status_valid",
        ),
        CheckConstraint("grams >= 0", name="bag_grams_not_negative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    material: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    collector_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resident.id"), index=True)
    grams: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = _now()
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


COLLECTION_STATES = ("authorized", "open", "closing", "closed", "expired", "failed")
COLLECTION_ACTIVE = ("authorized", "open", "closing")
_COLLECTION_ACTIVE_SQL = ", ".join(f"'{s}'" for s in COLLECTION_ACTIVE)


class Collection(Base):
    """A collector emptying one container into bags (docs/adr/0012).

    authorized -> open (lid opened) -> closing (collector done, or idle) -> closed (measured)
    authorized -> expired (the container never opened); closing -> failed (never measured)
    """

    __tablename__ = "collection"
    __table_args__ = (
        CheckConstraint(
            "state IN (" + ", ".join(f"'{s}'" for s in COLLECTION_STATES) + ")",
            name="collection_state_valid",
        ),
        Index(
            "one_active_collection_per_container",
            "container_id",
            unique=True,
            postgresql_where=text(f"state IN ({_COLLECTION_ACTIVE_SQL})"),
        ),
        Index("collection_state_idx", "state"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    container_id: Mapped[str] = mapped_column(ForeignKey("container.id"), index=True)
    collector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    state: Mapped[str] = mapped_column(String(16))
    # Scale readings: when the lid opened, the latest, and the final one after it closed.
    tare_g: Mapped[int | None] = mapped_column(Integer)
    last_weight_g: Mapped[int | None] = mapped_column(Integer)
    final_g: Mapped[int | None] = mapped_column(Integer)
    # What the container should have weighed when it opened, from its previous collection and the
    # deposits since then. None when there is nothing to compare with yet.
    expected_g: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    last_activity_at: Mapped[datetime] = _now()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollectionFill(Base):
    """One material taken out of the container during a collection: into a bag, or as residue
    (`bag_id` None). Weighed by the container's scale: `start_g - end_g`, or 0 when that is below
    the scale's noise threshold (`weight_change_g`, docs/adr/0012 amendments)."""

    __tablename__ = "collection_fill"
    __table_args__ = (
        # One material at a time: at most one fill still open per collection.
        Index(
            "one_open_fill_per_collection",
            "collection_id",
            unique=True,
            postgresql_where=text("end_g IS NULL"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection.id"), index=True)
    bag_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bag.id"), index=True)
    material: Mapped[str | None] = mapped_column(String(32))  # the bag's; None for residue
    start_g: Mapped[int] = mapped_column(Integer)
    end_g: Mapped[int | None] = mapped_column(Integer)
    grams: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = _now()
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


INCIDENT_KINDS = ("container_balance", "collection_balance", "bag_balance")
INCIDENT_STATUSES = ("open", "resolved")


class Incident(Base):
    """A mass balance that did not hold (docs/adr/0012). Bags named in an open incident are not
    sold or settled until the operator resolves it."""

    __tablename__ = "incident"
    __table_args__ = (
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in INCIDENT_KINDS) + ")",
            name="incident_kind_valid",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in INCIDENT_STATUSES) + ")",
            name="incident_status_valid",
        ),
        Index("incident_status_idx", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    container_id: Mapped[str | None] = mapped_column(ForeignKey("container.id"))
    collection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection.id"))
    bag_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID), default=list, server_default=text("'{}'")
    )
    expected_g: Mapped[int] = mapped_column(Integer)
    measured_g: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(254))
    resolution_note: Mapped[str | None] = mapped_column(Text)


SALE_STATUSES = ("recorded", "confirmed")
LINE_STATUSES = ("pending", "waiting", "settling", "settled", "failed")


class Sale(Base):
    """A buyer's ticket for one or more bags (docs/adr/0013). `confirmed` once the operator saw the
    money in the bank; only then is anything recorded on chain."""

    __tablename__ = "sale"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in SALE_STATUSES) + ")",
            name="sale_status_valid",
        ),
        CheckConstraint("total_cop > 0", name="sale_total_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    buyer: Mapped[str] = mapped_column(String(200))
    ticket_ref: Mapped[str] = mapped_column(String(100))
    sold_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_cop: Mapped[int] = mapped_column(BigInteger)
    # sha256 of the ticket's canonical JSON: the evidence each on-chain sale carries.
    evidence_hash: Mapped[str] = mapped_column(String(66))
    status: Mapped[str] = mapped_column(String(16))
    recorded_by: Mapped[str] = mapped_column(String(254))
    bank_ref: Mapped[str | None] = mapped_column(String(100))
    confirmed_by: Mapped[str | None] = mapped_column(String(254))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class SaleLine(Base):
    """One bag of a sale, settled on chain as a sale of its own (docs/adr/0013).

    pending | waiting -> settling (claimed by the worker) -> settled | waiting | pending | failed
    settling goes to waiting when a precondition is not met yet, back to pending after a network
    error, and is claimed again if a worker died while it was settling.
    """

    __tablename__ = "sale_line"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in LINE_STATUSES) + ")",
            name="sale_line_status_valid",
        ),
        CheckConstraint("amount_cop > 0", name="sale_line_amount_positive"),
        CheckConstraint("buyer_g > 0", name="sale_line_buyer_g_positive"),
        Index("sale_line_due_idx", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sale.id"), index=True)
    bag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bag.id"), unique=True)
    buyer_g: Mapped[int] = mapped_column(Integer)
    amount_cop: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    # Why it is waiting, or why it failed.
    reason: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The parts paid, in pesos, once known.
    residents_cop: Mapped[int | None] = mapped_column(BigInteger)
    collector_cop: Mapped[int | None] = mapped_column(BigInteger)
    host_cop: Mapped[int | None] = mapped_column(BigInteger)
    # Transactions, in the order they were sent.
    txs: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'"))
    report_hash: Mapped[str | None] = mapped_column(String(66))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class Settlement(Base):
    """What one party got from one sale line: a deposit's share (and what was paid on top of its
    advance), the collector's part, or a host's part. The published settlement report."""

    __tablename__ = "settlement"
    __table_args__ = (
        CheckConstraint("party IN ('deposit', 'collector', 'host')", name="settlement_party_valid"),
        Index("one_settlement_per_party", "line_id", "party", "party_ref", unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sale_line.id"), index=True)
    party: Mapped[str] = mapped_column(String(16))
    # The deposit session id, the collector's resident id or the host id.
    party_ref: Mapped[str] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(42))
    grams: Mapped[int] = mapped_column(Integer)
    share_cop: Mapped[int] = mapped_column(BigInteger)
    # For deposits: the share minus the advance; otherwise the share. None until paid.
    paid_cop: Mapped[int | None] = mapped_column(BigInteger)
    tx_hash: Mapped[str | None] = mapped_column(String(66))
    created_at: Mapped[datetime] = _now()


OPERATOR_ROLES = ("admin", "operator")


class Operator(Base):
    """A person who runs Zyrcle from the console (docs/adr/0014). Signs in with an email code."""

    __tablename__ = "operator"
    __table_args__ = (
        CheckConstraint(
            "role IN (" + ", ".join(f"'{r}'" for r in OPERATOR_ROLES) + ")",
            name="operator_role_valid",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


class OperatorCode(Base):
    """A sign-in code sent to an operator's email. Keyed by the address, not the operator, so an
    address that belongs to nobody is limited and answered exactly like one that does."""

    __tablename__ = "operator_code"
    __table_args__ = (Index("operator_code_lookup_idx", "email", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()


CERTIFICATE_STATUSES = ("issued", "anchored", "failed")


class Certificate(Base):
    """A host's (or one of its sites') impact certificate for a month (docs/adr/0027).

    issued -> anchored (root written on chain by the anchor worker) | failed
    """

    __tablename__ = "certificate"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in CERTIFICATE_STATUSES) + ")",
            name="certificate_status_valid",
        ),
        CheckConstraint("period ~ '^[0-9]{4}-[0-9]{2}$'", name="certificate_period_valid"),
        Index("certificate_host_period_idx", "host_id", "period"),
        Index("certificate_due_idx", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("host.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("site.id"))
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM, local time
    factors_version: Mapped[str] = mapped_column(String(16))
    deposits: Mapped[int] = mapped_column(Integer)
    participants: Mapped[int] = mapped_column(Integer)
    grams: Mapped[int] = mapped_column(BigInteger)
    co2e_g: Mapped[int] = mapped_column(BigInteger)
    # {material: {"grams": int, "co2e_g": int}}
    by_material: Mapped[dict] = mapped_column(JSONB)
    merkle_root: Mapped[str] = mapped_column(String(66))
    status: Mapped[str] = mapped_column(String(16))
    anchor_tx: Mapped[str | None] = mapped_column(String(66))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    issued_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = _now()
    anchored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImpactClaim(Base):
    """An environmental attribute of a deposit, claimed once (docs/adr/0027): the same gram is
    never reported twice for the same attribute. v1 has one attribute, `co2e`."""

    __tablename__ = "impact_claim"
    __table_args__ = (
        CheckConstraint("attribute IN ('co2e')", name="impact_claim_attribute_valid"),
        Index("one_claim_per_deposit_attribute", "session_id", "attribute", unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deposit_session.id"))
    attribute: Mapped[str] = mapped_column(String(16))
    certificate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("certificate.id"), index=True)
    grams: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _now()


class Merchant(Base):
    """A participant the operator named a merchant (docs/adr/0029): paid at the same account, and
    able to redeem ZYR for pesos once its KYC (`nit`, checked off line) is done."""

    __tablename__ = "merchant"
    resident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    nit: Mapped[str] = mapped_column(String(32))
    host_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("host.id"))
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = _now()


PAYMENT_STATUSES = ("open", "paying", "paid", "failed", "expired")


class PaymentRequest(Base):
    """A merchant's charge, paid by a participant's signed `Execute` that the backend relays
    (docs/adr/0029).

    open -> paying (signed, waiting for the relay) -> paid | failed;  open -> expired
    """

    __tablename__ = "payment_request"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in PAYMENT_STATUSES) + ")",
            name="payment_request_status_valid",
        ),
        CheckConstraint("amount_cop > 0", name="payment_request_amount_positive"),
        # One payment in flight per payer, so their account's nonces do not collide.
        Index(
            "one_payment_in_flight_per_payer",
            "payer_id",
            unique=True,
            postgresql_where=text("status = 'paying'"),
        ),
        Index("payment_request_due_idx", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    amount_cop: Mapped[int] = mapped_column(BigInteger)
    concept: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16))
    payer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resident.id"), index=True)
    signature: Mapped[str | None] = mapped_column(String(200))
    deadline: Mapped[int | None] = mapped_column(BigInteger)
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    tx_hash: Mapped[str | None] = mapped_column(String(66))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


REDEMPTION_STATUSES = ("signing", "requested", "pending", "settled", "refunded", "failed")


class RedemptionRequest(Base):
    """A merchant turning ZYR into pesos (docs/adr/0029).

    signing (intent made) -> requested (signed, waiting for the relay) -> pending (on chain, waiting
    for the operator's bank transfer) -> settled | refunded;  requested -> failed
    """

    __tablename__ = "redemption_request"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in REDEMPTION_STATUSES) + ")",
            name="redemption_request_status_valid",
        ),
        CheckConstraint("amount_cop > 0", name="redemption_request_amount_positive"),
        Index("redemption_request_due_idx", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resident.id"), index=True)
    amount_cop: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    signature: Mapped[str | None] = mapped_column(String(200))
    deadline: Mapped[int | None] = mapped_column(BigInteger)
    nonce: Mapped[int | None] = mapped_column(BigInteger)
    request_tx: Mapped[str | None] = mapped_column(String(66))
    decision_tx: Mapped[str | None] = mapped_column(String(66))
    bank_ref: Mapped[str | None] = mapped_column(String(100))
    decided_by: Mapped[str | None] = mapped_column(String(254))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()

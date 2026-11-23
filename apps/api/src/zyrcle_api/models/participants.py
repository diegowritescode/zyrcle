"""Participants, their sign-in, push tokens, emailed codes and account recovery (docs/adr/0010)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now


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

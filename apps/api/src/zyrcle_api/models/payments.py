"""Campus merchants, payments and redemptions (docs/adr/0029)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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

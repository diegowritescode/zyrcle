"""Reference prices and advances paid on chain (docs/adr/0007)."""

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

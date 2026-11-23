"""Sales to collection centers, their lines and settlements (docs/adr/0013)."""

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now

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
    # The collection center that bought, when it is one on record (ADR 0037).
    center_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_center.id"), index=True
    )
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

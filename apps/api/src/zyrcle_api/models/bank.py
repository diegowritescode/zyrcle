"""Bank statements the operator uploads, and their lines matched to sales and redemptions
(docs/adr/0039)."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now

BANK_MATCH_KINDS = ("sale", "redemption")


class BankStatement(Base):
    __tablename__ = "bank_statement"
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(200))
    file_sha256: Mapped[str] = mapped_column(String(64))
    lines: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[str] = mapped_column(String(254))
    created_at: Mapped[datetime] = _now()


class BankLine(Base):
    """One movement of the bank account. Credits pay sales, debits pay redemptions. The same
    movement in a second statement is recognised by its fingerprint and kept once."""

    __tablename__ = "bank_line"
    __table_args__ = (
        CheckConstraint(
            "matched_kind IS NULL OR matched_kind IN ("
            + ", ".join(f"'{k}'" for k in BANK_MATCH_KINDS)
            + ")",
            name="bank_line_matched_kind_valid",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    statement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bank_statement.id"), index=True)
    posted_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(300))
    reference: Mapped[str] = mapped_column(String(100))
    amount_cop: Mapped[int] = mapped_column(BigInteger)  # credits positive, debits negative
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    matched_kind: Mapped[str | None] = mapped_column(String(16))
    matched_id: Mapped[uuid.UUID | None] = mapped_column(UUID, unique=True)
    matched_by: Mapped[str | None] = mapped_column(String(254))
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()

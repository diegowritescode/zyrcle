"""Impact certificates and the claim ledger (docs/adr/0027)."""

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

CERTIFICATE_STATUSES = ("issued", "anchored", "failed")
MONTHLY_REPORT_STATUSES = ("waiting", "sent", "empty", "failed")


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
    # CID of the public copy on IPFS, pinned before anchoring when Pinata is configured; the
    # anchor then carries it too (amendment of 2026-11-22).
    ipfs_cid: Mapped[str | None] = mapped_column(String(100))
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


class MonthlyReport(Base):
    """A host's report for a month (docs/adr/0046), made once in the first days of the next:

    waiting (certificate issued, its anchor pending) -> sent (emailed with the PDF) | failed;
    empty: nothing sold that month, so no certificate and no email.
    """

    __tablename__ = "monthly_report"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in MONTHLY_REPORT_STATUSES) + ")",
            name="monthly_report_status_valid",
        ),
        CheckConstraint("period ~ '^[0-9]{4}-[0-9]{2}$'", name="monthly_report_period_valid"),
        Index("one_report_per_host_month", "host_id", "period", unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("host.id"))
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM, local time
    status: Mapped[str] = mapped_column(String(16))
    certificate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("certificate.id"))
    recipients: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

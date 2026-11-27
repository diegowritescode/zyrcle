"""Outboxes of push notifications and emails (docs/adr/0008, 0010)."""

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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, _now

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
    # Files sent with it: [{filename, content_type, content_b64}], such as the monthly certificate's
    # PDF (docs/adr/0046). Cleared once the email is sent or given up on.
    attachments: Mapped[list | None] = mapped_column(JSONB)

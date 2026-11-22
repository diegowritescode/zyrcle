"""time slots, push tokens and the notification outbox

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    # Existing residences stay open all day with 20 spots per container and hour.
    op.add_column(
        "residence",
        sa.Column("opens_hour", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "residence",
        sa.Column("closes_hour", sa.SmallInteger(), server_default=sa.text("24"), nullable=False),
    )
    op.add_column(
        "residence",
        sa.Column("slot_capacity", sa.SmallInteger(), server_default=sa.text("20"), nullable=False),
    )
    op.create_check_constraint(
        "residence_hours_valid",
        "residence",
        "0 <= opens_hour AND opens_hour < closes_hour AND closes_hour <= 24",
    )
    op.create_check_constraint("residence_slot_capacity_positive", "residence", "slot_capacity > 0")

    op.create_table(
        "booking",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("container_id", sa.String(length=64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("walk_in", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint("status IN ('booked', 'cancelled')", name="booking_status_valid"),
        sa.ForeignKeyConstraint(["container_id"], ["container.id"]),
        sa.ForeignKeyConstraint(["resident_id"], ["resident.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("booking_slot_idx", "booking", ["container_id", "starts_at"])
    op.create_index(op.f("ix_booking_resident_id"), "booking", ["resident_id"])
    op.create_index(
        "one_booking_per_resident_slot",
        "booking",
        ["resident_id", "container_id", "starts_at"],
        unique=True,
        postgresql_where=sa.text("status = 'booked'"),
    )

    op.create_table(
        "push_token",
        sa.Column("token", sa.String(length=200), nullable=False),
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["resident_id"], ["resident.id"]),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_index(op.f("ix_push_token_resident_id"), "push_token", ["resident_id"])

    op.create_table(
        "notification",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=400), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tickets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("receipts_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'skipped', 'failed')",
            name="notification_status_valid",
        ),
        sa.ForeignKeyConstraint(["resident_id"], ["resident.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("notification_due_idx", "notification", ["status", "next_attempt_at"])
    op.create_index(op.f("ix_notification_resident_id"), "notification", ["resident_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_resident_id"), table_name="notification")
    op.drop_index("notification_due_idx", table_name="notification")
    op.drop_table("notification")
    op.drop_index(op.f("ix_push_token_resident_id"), table_name="push_token")
    op.drop_table("push_token")
    op.drop_index("one_booking_per_resident_slot", table_name="booking")
    op.drop_index(op.f("ix_booking_resident_id"), table_name="booking")
    op.drop_index("booking_slot_idx", table_name="booking")
    op.drop_table("booking")
    op.drop_constraint("residence_slot_capacity_positive", "residence", type_="check")
    op.drop_constraint("residence_hours_valid", "residence", type_="check")
    op.drop_column("residence", "slot_capacity")
    op.drop_column("residence", "closes_hour")
    op.drop_column("residence", "opens_hour")

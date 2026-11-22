"""smart accounts: phone key per resident, recovery email, account recovery, email outbox

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-22 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LIVE = "status IN ('starting', 'waiting', 'cancelling')"


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    # Existing residents signed in with the key that also held their ZYR: that key is their owner.
    # They get a smart account the next time they sign in (auth.py).
    op.add_column("resident", sa.Column("owner_address", sa.String(length=42), nullable=True))
    op.execute("UPDATE resident SET owner_address = address")
    op.alter_column("resident", "owner_address", nullable=False)
    op.create_unique_constraint("resident_owner_address_key", "resident", ["owner_address"])
    op.add_column("resident", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column(
        "resident", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint("resident_email_key", "resident", ["email"])

    op.create_table(
        "email_code",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        sa.CheckConstraint("purpose IN ('verify', 'recover')", name="email_code_purpose_valid"),
        sa.ForeignKeyConstraint(["resident_id"], ["resident.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("email_code_lookup_idx", "email_code", ["email", "purpose", "created_at"])
    op.create_index(op.f("ix_email_code_resident_id"), "email_code", ["resident_id"])

    op.create_table(
        "account_recovery",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("new_resident_id", sa.UUID(), nullable=True),
        sa.Column("account_address", sa.String(length=42), nullable=False),
        sa.Column("new_owner", sa.String(length=42), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_by", sa.String(length=16), nullable=True),
        sa.Column("start_tx", sa.String(length=66), nullable=True),
        sa.Column("finish_tx", sa.String(length=66), nullable=True),
        sa.Column("cancel_tx", sa.String(length=66), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(
            "status IN ('starting', 'waiting', 'cancelling', 'done', 'cancelled', 'failed')",
            name="account_recovery_status_valid",
        ),
        sa.ForeignKeyConstraint(["resident_id"], ["resident.id"]),
        sa.ForeignKeyConstraint(["new_resident_id"], ["resident.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_recovery_resident_id"), "account_recovery", ["resident_id"])
    op.create_index("account_recovery_due_idx", "account_recovery", ["status", "next_attempt_at"])
    op.create_index(
        "one_live_recovery_per_account",
        "account_recovery",
        ["resident_id"],
        unique=True,
        postgresql_where=sa.text(LIVE),
    )
    op.create_index(
        "one_live_recovery_per_new_phone",
        "account_recovery",
        ["new_resident_id"],
        unique=True,
        postgresql_where=sa.text(LIVE),
    )

    op.create_table(
        "email_message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=120), nullable=False),
        sa.Column("to", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name="email_message_status_valid"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index("email_message_due_idx", "email_message", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("email_message_due_idx", table_name="email_message")
    op.drop_table("email_message")
    op.drop_index("one_live_recovery_per_new_phone", table_name="account_recovery")
    op.drop_index("one_live_recovery_per_account", table_name="account_recovery")
    op.drop_index("account_recovery_due_idx", table_name="account_recovery")
    op.drop_index(op.f("ix_account_recovery_resident_id"), table_name="account_recovery")
    op.drop_table("account_recovery")
    op.drop_index(op.f("ix_email_code_resident_id"), table_name="email_code")
    op.drop_index("email_code_lookup_idx", table_name="email_code")
    op.drop_table("email_code")
    op.drop_constraint("resident_email_key", "resident", type_="unique")
    op.drop_column("resident", "email_verified_at")
    op.drop_column("resident", "email")
    op.drop_constraint("resident_owner_address_key", "resident", type_="unique")
    op.drop_column("resident", "owner_address")

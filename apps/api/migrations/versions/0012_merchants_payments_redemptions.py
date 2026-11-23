"""merchants, their charges, and redemptions of ZYR for pesos (docs/adr/0029)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-23 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "merchant",
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("nit", sa.String(length=32), nullable=False),
        sa.Column("host_id", sa.UUID(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["host.id"],
        ),
        sa.ForeignKeyConstraint(
            ["resident_id"],
            ["resident.id"],
        ),
        sa.PrimaryKeyConstraint("resident_id"),
    )
    op.create_table(
        "payment_request",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("amount_cop", sa.BigInteger(), nullable=False),
        sa.Column("concept", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("payer_id", sa.UUID(), nullable=True),
        sa.Column("signature", sa.String(length=200), nullable=True),
        sa.Column("deadline", sa.BigInteger(), nullable=True),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'paying', 'paid', 'failed', 'expired')",
            name="payment_request_status_valid",
        ),
        sa.CheckConstraint("amount_cop > 0", name="payment_request_amount_positive"),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["resident.id"],
        ),
        sa.ForeignKeyConstraint(
            ["payer_id"],
            ["resident.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_request_merchant_id"), "payment_request", ["merchant_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_request_payer_id"), "payment_request", ["payer_id"], unique=False
    )
    op.create_index(
        "one_payment_in_flight_per_payer",
        "payment_request",
        ["payer_id"],
        unique=True,
        postgresql_where=sa.text("status = 'paying'"),
    )
    op.create_index(
        "payment_request_due_idx", "payment_request", ["status", "next_attempt_at"], unique=False
    )
    op.create_table(
        "redemption_request",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("amount_cop", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("signature", sa.String(length=200), nullable=True),
        sa.Column("deadline", sa.BigInteger(), nullable=True),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("request_tx", sa.String(length=66), nullable=True),
        sa.Column("decision_tx", sa.String(length=66), nullable=True),
        sa.Column("bank_ref", sa.String(length=100), nullable=True),
        sa.Column("decided_by", sa.String(length=254), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('signing', 'requested', 'pending', 'settled', 'refunded', 'failed')",
            name="redemption_request_status_valid",
        ),
        sa.CheckConstraint("amount_cop > 0", name="redemption_request_amount_positive"),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["resident.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_redemption_request_merchant_id"),
        "redemption_request",
        ["merchant_id"],
        unique=False,
    )
    op.create_index(
        "redemption_request_due_idx",
        "redemption_request",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("redemption_request_due_idx", table_name="redemption_request")
    op.drop_index(op.f("ix_redemption_request_merchant_id"), table_name="redemption_request")
    op.drop_table("redemption_request")
    op.drop_index("payment_request_due_idx", table_name="payment_request")
    op.drop_index(
        "one_payment_in_flight_per_payer",
        table_name="payment_request",
        postgresql_where=sa.text("status = 'paying'"),
    )
    op.drop_index(op.f("ix_payment_request_payer_id"), table_name="payment_request")
    op.drop_index(op.f("ix_payment_request_merchant_id"), table_name="payment_request")
    op.drop_table("payment_request")
    op.drop_table("merchant")

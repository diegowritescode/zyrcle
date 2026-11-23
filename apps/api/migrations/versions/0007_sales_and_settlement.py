"""sales, their bags and the settlement report (docs/adr/0013)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sale",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("buyer", sa.String(length=200), nullable=False),
        sa.Column("ticket_ref", sa.String(length=100), nullable=False),
        sa.Column("sold_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cop", sa.BigInteger(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=66), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recorded_by", sa.String(length=64), nullable=False),
        sa.Column("bank_ref", sa.String(length=100), nullable=True),
        sa.Column("confirmed_by", sa.String(length=64), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('recorded', 'confirmed')", name="sale_status_valid"),
        sa.CheckConstraint("total_cop > 0", name="sale_total_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sale_line",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("sale_id", sa.UUID(), nullable=False),
        sa.Column("bag_id", sa.UUID(), nullable=False),
        sa.Column("buyer_g", sa.Integer(), nullable=False),
        sa.Column("amount_cop", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("residents_cop", sa.BigInteger(), nullable=True),
        sa.Column("collector_cop", sa.BigInteger(), nullable=True),
        sa.Column("host_cop", sa.BigInteger(), nullable=True),
        sa.Column(
            "txs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("report_hash", sa.String(length=66), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('pending', 'waiting', 'settling', 'settled', 'failed')",
            name="sale_line_status_valid",
        ),
        sa.CheckConstraint("amount_cop > 0", name="sale_line_amount_positive"),
        sa.CheckConstraint("buyer_g > 0", name="sale_line_buyer_g_positive"),
        sa.ForeignKeyConstraint(
            ["bag_id"],
            ["bag.id"],
        ),
        sa.ForeignKeyConstraint(
            ["sale_id"],
            ["sale.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bag_id"),
    )
    op.create_index(op.f("ix_sale_line_sale_id"), "sale_line", ["sale_id"], unique=False)
    op.create_index("sale_line_due_idx", "sale_line", ["status", "next_attempt_at"], unique=False)
    op.create_table(
        "settlement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("line_id", sa.UUID(), nullable=False),
        sa.Column("party", sa.String(length=16), nullable=False),
        sa.Column("party_ref", sa.String(length=64), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=True),
        sa.Column("grams", sa.Integer(), nullable=False),
        sa.Column("share_cop", sa.BigInteger(), nullable=False),
        sa.Column("paid_cop", sa.BigInteger(), nullable=True),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "party IN ('deposit', 'collector', 'host')", name="settlement_party_valid"
        ),
        sa.ForeignKeyConstraint(
            ["line_id"],
            ["sale_line.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_settlement_line_id"), "settlement", ["line_id"], unique=False)
    op.create_index(
        "one_settlement_per_party", "settlement", ["line_id", "party", "party_ref"], unique=True
    )


def downgrade() -> None:
    op.drop_index("one_settlement_per_party", table_name="settlement")
    op.drop_index(op.f("ix_settlement_line_id"), table_name="settlement")
    op.drop_table("settlement")
    op.drop_index("sale_line_due_idx", table_name="sale_line")
    op.drop_index(op.f("ix_sale_line_sale_id"), table_name="sale_line")
    op.drop_table("sale_line")
    op.drop_table("sale")

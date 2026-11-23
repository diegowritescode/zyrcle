"""bank statements and their lines, matched to sales and redemptions (docs/adr/0039)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-23 09:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_statement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("lines", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=254), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bank_line",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("statement_id", sa.UUID(), nullable=False),
        sa.Column("posted_on", sa.Date(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("amount_cop", sa.BigInteger(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("matched_kind", sa.String(length=16), nullable=True),
        sa.Column("matched_id", sa.UUID(), nullable=True),
        sa.Column("matched_by", sa.String(length=254), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "matched_kind IS NULL OR matched_kind IN ('sale', 'redemption')",
            name="bank_line_matched_kind_valid",
        ),
        sa.ForeignKeyConstraint(
            ["statement_id"],
            ["bank_statement.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
        sa.UniqueConstraint("matched_id"),
    )
    op.create_index(op.f("ix_bank_line_statement_id"), "bank_line", ["statement_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bank_line_statement_id"), table_name="bank_line")
    op.drop_table("bank_line")
    op.drop_table("bank_statement")

"""impact certificates and the claim ledger (docs/adr/0027)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-22 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "certificate",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("host_id", sa.UUID(), nullable=False),
        sa.Column("site_id", sa.UUID(), nullable=True),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("factors_version", sa.String(length=16), nullable=False),
        sa.Column("deposits", sa.Integer(), nullable=False),
        sa.Column("participants", sa.Integer(), nullable=False),
        sa.Column("grams", sa.BigInteger(), nullable=False),
        sa.Column("co2e_g", sa.BigInteger(), nullable=False),
        sa.Column("by_material", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("merkle_root", sa.String(length=66), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("anchor_tx", sa.String(length=66), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("issued_by", sa.String(length=254), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("anchored_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("period ~ '^[0-9]{4}-[0-9]{2}$'", name="certificate_period_valid"),
        sa.CheckConstraint(
            "status IN ('issued', 'anchored', 'failed')", name="certificate_status_valid"
        ),
        sa.ForeignKeyConstraint(
            ["host_id"],
            ["host.id"],
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["site.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "certificate_due_idx", "certificate", ["status", "next_attempt_at"], unique=False
    )
    op.create_index(
        "certificate_host_period_idx", "certificate", ["host_id", "period"], unique=False
    )
    op.create_table(
        "impact_claim",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("attribute", sa.String(length=16), nullable=False),
        sa.Column("certificate_id", sa.UUID(), nullable=False),
        sa.Column("grams", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attribute IN ('co2e')", name="impact_claim_attribute_valid"),
        sa.ForeignKeyConstraint(
            ["certificate_id"],
            ["certificate.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["deposit_session.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_impact_claim_certificate_id"), "impact_claim", ["certificate_id"], unique=False
    )
    op.create_index(
        "one_claim_per_deposit_attribute", "impact_claim", ["session_id", "attribute"], unique=True
    )


def downgrade() -> None:
    op.drop_index("one_claim_per_deposit_attribute", table_name="impact_claim")
    op.drop_index(op.f("ix_impact_claim_certificate_id"), table_name="impact_claim")
    op.drop_table("impact_claim")
    op.drop_index("certificate_host_period_idx", table_name="certificate")
    op.drop_index("certificate_due_idx", table_name="certificate")
    op.drop_table("certificate")

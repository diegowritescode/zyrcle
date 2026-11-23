"""scale ticket photos and what the model read from them (docs/adr/0038)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-23 08:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_scan",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("reading", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=254), nullable=False),
        sa.Column("sale_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('read', 'failed')", name="ticket_scan_status_valid"),
        sa.ForeignKeyConstraint(["sale_id"], ["sale.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_scan_image_sha256", "ticket_scan", ["image_sha256"])
    op.create_index("ix_ticket_scan_sale_id", "ticket_scan", ["sale_id"])


def downgrade() -> None:
    op.drop_table("ticket_scan")

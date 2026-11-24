"""where to spend, fill readings of collections and a collector's host (docs/adr/0041, 0042)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-24 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ADR 0041: what a participant needs to find a campus merchant.
    op.add_column("merchant", sa.Column("site_id", sa.UUID(), nullable=True))
    op.create_foreign_key("merchant_site_id_fkey", "merchant", "site", ["site_id"], ["id"])
    op.add_column("merchant", sa.Column("place", sa.String(length=200), nullable=True))
    op.add_column("merchant", sa.Column("hours", sa.String(length=120), nullable=True))
    op.add_column("merchant", sa.Column("offer", sa.String(length=300), nullable=True))
    # ADR 0042: the distance sensor's reading after a collection, and the host a collector serves.
    op.add_column("collection", sa.Column("fill_after_mm", sa.Integer(), nullable=True))
    op.add_column("collector", sa.Column("host_id", sa.UUID(), nullable=True))
    op.create_foreign_key("collector_host_id_fkey", "collector", "host", ["host_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("collector_host_id_fkey", "collector", type_="foreignkey")
    op.drop_column("collector", "host_id")
    op.drop_column("collection", "fill_after_mm")
    op.drop_column("merchant", "offer")
    op.drop_column("merchant", "hours")
    op.drop_column("merchant", "place")
    op.drop_constraint("merchant_site_id_fkey", "merchant", type_="foreignkey")
    op.drop_column("merchant", "site_id")

"""collection centers, their prices per material, and the center of each site and sale
(docs/adr/0037)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-23 07:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "collection_center",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tax_id", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("contact", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "center_price",
        sa.Column("center_id", sa.UUID(), nullable=False),
        sa.Column("material", sa.String(length=32), nullable=False),
        sa.Column("cop_per_kg", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("updated_by", sa.String(length=254), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("source IN ('manual', 'sales')", name="center_price_source_valid"),
        sa.CheckConstraint("cop_per_kg >= 0", name="center_price_cop_per_kg_check"),
        sa.ForeignKeyConstraint(["center_id"], ["collection_center.id"]),
        sa.PrimaryKeyConstraint("center_id", "material"),
    )
    for table in ("site", "sale"):
        op.add_column(table, sa.Column("center_id", sa.UUID(), nullable=True))
        op.create_index(f"ix_{table}_center_id", table, ["center_id"])
        op.create_foreign_key(
            f"{table}_center_id_fkey", table, "collection_center", ["center_id"], ["id"]
        )


def downgrade() -> None:
    for table in ("sale", "site"):
        op.drop_constraint(f"{table}_center_id_fkey", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_center_id", table_name=table)
        op.drop_column(table, "center_id")
    op.drop_table("center_price")
    op.drop_table("collection_center")

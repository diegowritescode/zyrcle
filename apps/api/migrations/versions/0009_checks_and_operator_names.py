"""checks the models declared but no migration created; room for operators' emails

Found while documenting the database (docs/database.md, "Discrepancies"):
- container.area_mm2 > 0, container.depth_mm > 0 and material_price.cop_per_kg >= 0 were declared
  in the models but never created, so the database did not enforce them;
- the columns that record which operator acted held 64 characters, and an operator's email can
  have up to 254 (docs/adr/0014).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-22 21:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = [
    ("container_area_mm2_check", "container", "area_mm2 > 0"),
    ("container_depth_mm_check", "container", "depth_mm > 0"),
    ("material_price_cop_per_kg_check", "material_price", "cop_per_kg >= 0"),
]
WHO = [
    ("deposit_session", "reviewed_by"),
    ("incident", "resolved_by"),
    ("sale", "recorded_by"),
    ("sale", "confirmed_by"),
]


def upgrade() -> None:
    for name, table, condition in CHECKS:
        op.create_check_constraint(name, table, condition)
    for table, column in WHO:
        op.alter_column(table, column, type_=sa.String(length=254), existing_type=sa.String(64))


def downgrade() -> None:
    for table, column in WHO:
        op.alter_column(table, column, type_=sa.String(length=64), existing_type=sa.String(254))
    for name, table, _ in CHECKS:
        op.drop_constraint(name, table, type_="check")

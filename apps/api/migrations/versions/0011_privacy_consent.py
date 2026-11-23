"""the data-processing policy each participant accepted, Ley 1581 (docs/adr/0028)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-23 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resident", sa.Column("privacy_version", sa.String(length=16), nullable=True))
    op.add_column(
        "resident", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("resident", "privacy_accepted_at")
    op.drop_column("resident", "privacy_version")

"""the IPFS copy of each impact certificate (docs/adr/0027, amendment of 2026-11-22)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-23 03:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("certificate", sa.Column("ipfs_cid", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("certificate", "ipfs_cid")

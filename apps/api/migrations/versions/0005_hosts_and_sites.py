"""hosts and sites: residence becomes site, each site belongs to a host (docs/adr/0011)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-22 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "kind IN ('university', 'residential', 'business', 'public')"


def upgrade() -> None:
    op.create_table(
        "host",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("payout_address", sa.String(length=42), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(KINDS, name="host_kind_valid"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every residence becomes a site of its own host, with the same id: no mapping table needed.
    op.execute(
        "INSERT INTO host (id, name, kind, created_at) "
        "SELECT id, name, 'residential', created_at FROM residence"
    )

    op.rename_table("residence", "site")
    op.execute("ALTER INDEX residence_pkey RENAME TO site_pkey")
    op.execute("ALTER TABLE site RENAME CONSTRAINT residence_hours_valid TO site_hours_valid")
    op.execute(
        "ALTER TABLE site RENAME CONSTRAINT residence_slot_capacity_positive "
        "TO site_slot_capacity_positive"
    )
    op.add_column("site", sa.Column("host_id", sa.UUID(), nullable=True))
    op.execute("UPDATE site SET host_id = id")
    op.alter_column("site", "host_id", nullable=False)
    op.create_foreign_key("site_host_id_fkey", "site", "host", ["host_id"], ["id"])
    op.create_index(op.f("ix_site_host_id"), "site", ["host_id"])

    op.alter_column("container", "residence_id", new_column_name="site_id")
    op.execute(
        "ALTER TABLE container RENAME CONSTRAINT container_residence_id_fkey "
        "TO container_site_id_fkey"
    )
    op.create_index(op.f("ix_container_site_id"), "container", ["site_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_container_site_id"), table_name="container")
    op.execute(
        "ALTER TABLE container RENAME CONSTRAINT container_site_id_fkey "
        "TO container_residence_id_fkey"
    )
    op.alter_column("container", "site_id", new_column_name="residence_id")
    op.drop_index(op.f("ix_site_host_id"), table_name="site")
    op.drop_constraint("site_host_id_fkey", "site", type_="foreignkey")
    op.drop_column("site", "host_id")
    op.execute(
        "ALTER TABLE site RENAME CONSTRAINT site_slot_capacity_positive "
        "TO residence_slot_capacity_positive"
    )
    op.execute("ALTER TABLE site RENAME CONSTRAINT site_hours_valid TO residence_hours_valid")
    op.execute("ALTER INDEX site_pkey RENAME TO residence_pkey")
    op.rename_table("site", "residence")
    op.drop_table("host")

"""collectors, bags, collections with their fills, incidents (docs/adr/0012)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bag",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("material", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("collector_id", sa.UUID(), nullable=True),
        sa.Column("grams", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'sealed', 'sold', 'settled')", name="bag_status_valid"
        ),
        sa.CheckConstraint("grams >= 0", name="bag_grams_not_negative"),
        sa.ForeignKeyConstraint(
            ["collector_id"],
            ["resident.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_bag_collector_id"), "bag", ["collector_id"], unique=False)
    op.create_table(
        "collector",
        sa.Column("resident_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["resident_id"],
            ["resident.id"],
        ),
        sa.PrimaryKeyConstraint("resident_id"),
    )
    op.create_table(
        "collection",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("container_id", sa.String(length=64), nullable=False),
        sa.Column("collector_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("tare_g", sa.Integer(), nullable=True),
        sa.Column("last_weight_g", sa.Integer(), nullable=True),
        sa.Column("final_g", sa.Integer(), nullable=True),
        sa.Column("expected_g", sa.Integer(), nullable=True),
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
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('authorized', 'open', 'closing', 'closed', 'expired', 'failed')",
            name="collection_state_valid",
        ),
        sa.ForeignKeyConstraint(
            ["collector_id"],
            ["resident.id"],
        ),
        sa.ForeignKeyConstraint(
            ["container_id"],
            ["container.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("collection_state_idx", "collection", ["state"], unique=False)
    op.create_index(
        op.f("ix_collection_collector_id"), "collection", ["collector_id"], unique=False
    )
    op.create_index(
        op.f("ix_collection_container_id"), "collection", ["container_id"], unique=False
    )
    op.create_index(
        "one_active_collection_per_container",
        "collection",
        ["container_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('authorized', 'open', 'closing')"),
    )
    op.create_table(
        "collection_fill",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("collection_id", sa.UUID(), nullable=False),
        sa.Column("bag_id", sa.UUID(), nullable=True),
        sa.Column("material", sa.String(length=32), nullable=True),
        sa.Column("start_g", sa.Integer(), nullable=False),
        sa.Column("end_g", sa.Integer(), nullable=True),
        sa.Column("grams", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["bag_id"],
            ["bag.id"],
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collection.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_collection_fill_bag_id"), "collection_fill", ["bag_id"], unique=False)
    op.create_index(
        op.f("ix_collection_fill_collection_id"), "collection_fill", ["collection_id"], unique=False
    )
    op.create_index(
        "one_open_fill_per_collection",
        "collection_fill",
        ["collection_id"],
        unique=True,
        postgresql_where=sa.text("end_g IS NULL"),
    )
    op.create_table(
        "incident",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("container_id", sa.String(length=64), nullable=True),
        sa.Column("collection_id", sa.UUID(), nullable=True),
        sa.Column(
            "bag_ids", postgresql.ARRAY(sa.UUID()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("expected_g", sa.Integer(), nullable=False),
        sa.Column("measured_g", sa.Integer(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('container_balance', 'collection_balance', 'bag_balance')",
            name="incident_kind_valid",
        ),
        sa.CheckConstraint("status IN ('open', 'resolved')", name="incident_status_valid"),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collection.id"],
        ),
        sa.ForeignKeyConstraint(
            ["container_id"],
            ["container.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("incident_status_idx", "incident", ["status"], unique=False)
    op.add_column("deposit_session", sa.Column("collection_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_deposit_session_collection_id"), "deposit_session", ["collection_id"], unique=False
    )
    op.create_foreign_key(
        "deposit_session_collection_id_fkey",
        "deposit_session",
        "collection",
        ["collection_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("deposit_session_collection_id_fkey", "deposit_session", type_="foreignkey")
    op.drop_index(op.f("ix_deposit_session_collection_id"), table_name="deposit_session")
    op.drop_column("deposit_session", "collection_id")
    op.drop_index("incident_status_idx", table_name="incident")
    op.drop_table("incident")
    op.drop_index(
        "one_open_fill_per_collection",
        table_name="collection_fill",
        postgresql_where=sa.text("end_g IS NULL"),
    )
    op.drop_index(op.f("ix_collection_fill_collection_id"), table_name="collection_fill")
    op.drop_index(op.f("ix_collection_fill_bag_id"), table_name="collection_fill")
    op.drop_table("collection_fill")
    op.drop_index(
        "one_active_collection_per_container",
        table_name="collection",
        postgresql_where=sa.text("state IN ('authorized', 'open', 'closing')"),
    )
    op.drop_index(op.f("ix_collection_container_id"), table_name="collection")
    op.drop_index(op.f("ix_collection_collector_id"), table_name="collection")
    op.drop_index("collection_state_idx", table_name="collection")
    op.drop_table("collection")
    op.drop_table("collector")
    op.drop_index(op.f("ix_bag_collector_id"), table_name="bag")
    op.drop_table("bag")

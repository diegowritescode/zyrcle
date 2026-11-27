"""monthly reports, report contacts, monthly goals and email attachments (docs/adr/0046)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-27 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "host",
        sa.Column("monthly_report", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "host",
        sa.Column(
            "report_emails",
            postgresql.ARRAY(sa.String(length=254)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.add_column("host", sa.Column("monthly_goal_kg", sa.Integer(), nullable=True))
    op.add_column("site", sa.Column("monthly_goal_kg", sa.Integer(), nullable=True))
    op.add_column(
        "email_message",
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "monthly_report",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("host_id", sa.UUID(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("certificate_id", sa.UUID(), nullable=True),
        sa.Column("recipients", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('waiting', 'sent', 'empty', 'failed')", name="monthly_report_status_valid"
        ),
        sa.CheckConstraint("period ~ '^[0-9]{4}-[0-9]{2}$'", name="monthly_report_period_valid"),
        sa.ForeignKeyConstraint(["certificate_id"], ["certificate.id"]),
        sa.ForeignKeyConstraint(["host_id"], ["host.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "one_report_per_host_month", "monthly_report", ["host_id", "period"], unique=True
    )


def downgrade() -> None:
    op.drop_index("one_report_per_host_month", table_name="monthly_report")
    op.drop_table("monthly_report")
    op.drop_column("email_message", "attachments")
    op.drop_column("site", "monthly_goal_kg")
    op.drop_column("host", "monthly_goal_kg")
    op.drop_column("host", "report_emails")
    op.drop_column("host", "monthly_report")

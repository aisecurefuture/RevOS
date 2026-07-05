"""scheduler event types + bookings (P3)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-05 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_event_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(140), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_notice_minutes", sa.Integer(), nullable=False, server_default="240"),
        sa.Column("max_days_ahead", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("weekly_availability", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("location_type", sa.String(16), nullable=False, server_default="custom"),
        sa.Column("location_detail", sa.String(500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduler_event_types_account_id", "scheduler_event_types", ["account_id"])
    op.create_index("ix_scheduler_event_types_created_by", "scheduler_event_types", ["created_by"])
    op.create_index("ix_scheduler_event_types_slug", "scheduler_event_types", ["slug"])
    op.create_index("ix_scheduler_event_types_active", "scheduler_event_types", ["active"])
    op.create_index("ix_scheduler_event_types_deleted_at", "scheduler_event_types", ["deleted_at"])

    op.create_table(
        "scheduler_bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("event_type_id", sa.Uuid(), nullable=False),
        sa.Column("invitee_name", sa.String(200), nullable=False),
        sa.Column("invitee_email", sa.String(320), nullable=False),
        sa.Column("invitee_timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("invitee_notes", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.Column("blocked_start_at", sa.DateTime(), nullable=False),
        sa.Column("blocked_end_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="confirmed"),
        sa.Column("location_type", sa.String(16), nullable=False, server_default="custom"),
        sa.Column("location_detail", sa.String(500), nullable=True),
        sa.Column("manage_token", sa.String(64), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_type_id"], ["scheduler_event_types.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scheduler_bookings_account_id", "scheduler_bookings", ["account_id"])
    op.create_index("ix_scheduler_bookings_event_type_id", "scheduler_bookings", ["event_type_id"])
    op.create_index("ix_scheduler_bookings_invitee_email", "scheduler_bookings", ["invitee_email"])
    op.create_index("ix_scheduler_bookings_start_at", "scheduler_bookings", ["start_at"])
    op.create_index("ix_scheduler_bookings_blocked_start_at", "scheduler_bookings", ["blocked_start_at"])
    op.create_index("ix_scheduler_bookings_blocked_end_at", "scheduler_bookings", ["blocked_end_at"])
    op.create_index("ix_scheduler_bookings_status", "scheduler_bookings", ["status"])
    op.create_index("ix_scheduler_bookings_manage_token", "scheduler_bookings", ["manage_token"])
    op.create_index("ix_scheduler_bookings_deleted_at", "scheduler_bookings", ["deleted_at"])
    # Partial unique index: only one confirmed booking per (event_type, slot).
    op.create_index(
        "uq_booking_confirmed_slot",
        "scheduler_bookings",
        ["event_type_id", "start_at"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )


def downgrade() -> None:
    op.drop_table("scheduler_bookings")
    op.drop_table("scheduler_event_types")

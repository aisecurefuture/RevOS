"""listing video studio: listing_video_jobs

Revision ID: 7e3a9d51f8b2
Revises: d5f28a1b6c94
Create Date: 2026-07-20 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7e3a9d51f8b2"
down_revision: str | None = "d5f28a1b6c94"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing_video_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("photo_paths", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("music_track", sa.String(200), nullable=False, server_default=""),
        sa.Column("speaker_name", sa.String(100), nullable=False),
        sa.Column("render_manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress_note", sa.String(300), nullable=True),
        sa.Column("estimated_seconds", sa.Integer(), nullable=True),
        sa.Column("output_path", sa.String(600), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_video_jobs_account_id", "listing_video_jobs", ["account_id"])
    op.create_index("ix_listing_video_jobs_brand_id", "listing_video_jobs", ["brand_id"])
    op.create_index("ix_listing_video_jobs_status", "listing_video_jobs", ["status"])
    op.create_index("ix_listing_video_jobs_created_by", "listing_video_jobs", ["created_by"])
    op.create_index("ix_listing_video_jobs_deleted_at", "listing_video_jobs", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("listing_video_jobs")

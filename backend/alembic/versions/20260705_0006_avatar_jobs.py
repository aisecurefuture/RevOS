"""avatar video generation jobs (P3-M3)

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-05 23:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "avatar_video_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("persona_identity_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("target_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
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
        sa.ForeignKeyConstraint(["persona_identity_id"], ["persona_identities.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_avatar_video_jobs_account_id", "avatar_video_jobs", ["account_id"])
    op.create_index("ix_avatar_video_jobs_persona_identity_id", "avatar_video_jobs", ["persona_identity_id"])
    op.create_index("ix_avatar_video_jobs_brand_id", "avatar_video_jobs", ["brand_id"])
    op.create_index("ix_avatar_video_jobs_status", "avatar_video_jobs", ["status"])
    op.create_index("ix_avatar_video_jobs_created_by", "avatar_video_jobs", ["created_by"])
    op.create_index("ix_avatar_video_jobs_deleted_at", "avatar_video_jobs", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("avatar_video_jobs")

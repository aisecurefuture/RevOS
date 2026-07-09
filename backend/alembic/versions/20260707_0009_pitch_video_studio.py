"""pitch video studio: brand design tokens + pitch_video_jobs

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-07 09:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("design_tokens", sa.JSON(), nullable=False, server_default="{}"))

    op.create_table(
        "pitch_video_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("aspect_ratio", sa.String(10), nullable=False, server_default="16:9"),
        sa.Column("voice_mode", sa.String(10), nullable=False),
        sa.Column("speaker_name", sa.String(100), nullable=True),
        sa.Column("persona_identity_id", sa.Uuid(), nullable=True),
        sa.Column("deck_spec", sa.JSON(), nullable=False),
        sa.Column("scene_manifest", sa.JSON(), nullable=False, server_default="[]"),
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
        sa.ForeignKeyConstraint(["persona_identity_id"], ["persona_identities.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pitch_video_jobs_account_id", "pitch_video_jobs", ["account_id"])
    op.create_index("ix_pitch_video_jobs_brand_id", "pitch_video_jobs", ["brand_id"])
    op.create_index("ix_pitch_video_jobs_persona_identity_id", "pitch_video_jobs", ["persona_identity_id"])
    op.create_index("ix_pitch_video_jobs_status", "pitch_video_jobs", ["status"])
    op.create_index("ix_pitch_video_jobs_created_by", "pitch_video_jobs", ["created_by"])
    op.create_index("ix_pitch_video_jobs_deleted_at", "pitch_video_jobs", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("pitch_video_jobs")
    op.drop_column("brands", "design_tokens")

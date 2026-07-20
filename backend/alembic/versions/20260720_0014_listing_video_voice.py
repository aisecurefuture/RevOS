"""listing video: persona voice narration (voice_mode + persona_identity_id)

Revision ID: 3b8f2c6d9a41
Revises: 7e3a9d51f8b2
Create Date: 2026-07-20 13:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b8f2c6d9a41"
down_revision: str | None = "7e3a9d51f8b2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listing_video_jobs",
        sa.Column("voice_mode", sa.String(10), nullable=False, server_default="stock"),
    )
    op.add_column("listing_video_jobs", sa.Column("persona_identity_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_listing_video_jobs_persona_identity_id",
        "listing_video_jobs", "persona_identities",
        ["persona_identity_id"], ["id"],
    )
    op.create_index(
        "ix_listing_video_jobs_persona_identity_id", "listing_video_jobs", ["persona_identity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_video_jobs_persona_identity_id", table_name="listing_video_jobs")
    op.drop_constraint(
        "fk_listing_video_jobs_persona_identity_id", "listing_video_jobs", type_="foreignkey",
    )
    op.drop_column("listing_video_jobs", "persona_identity_id")
    op.drop_column("listing_video_jobs", "voice_mode")

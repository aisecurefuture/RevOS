"""listing video: aspect_ratio (landscape default for new jobs)

Revision ID: 9c4e7f2a5d18
Revises: 3b8f2c6d9a41
Create Date: 2026-07-20 19:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9c4e7f2a5d18"
down_revision: str | None = "3b8f2c6d9a41"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows were all rendered portrait — record that truthfully; the
    # application default for NEW jobs is 16:9.
    op.add_column(
        "listing_video_jobs",
        sa.Column("aspect_ratio", sa.String(10), nullable=False, server_default="9:16"),
    )


def downgrade() -> None:
    op.drop_column("listing_video_jobs", "aspect_ratio")

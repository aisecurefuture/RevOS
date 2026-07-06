"""brand book: vision, anti-audience, core values, brand story, archetype, voice spectrum (P3)

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
Create Date: 2026-07-06 10:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brand_books", sa.Column("vision", sa.Text(), nullable=True))
    op.add_column("brand_books", sa.Column("audience_exclusions", sa.Text(), nullable=True))
    op.add_column("brand_books", sa.Column("core_values", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("brand_books", sa.Column("brand_story", sa.Text(), nullable=True))
    op.add_column("brand_books", sa.Column("brand_archetype", sa.String(20), nullable=True))
    op.add_column("brand_books", sa.Column("voice_spectrum", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("brand_books", "voice_spectrum")
    op.drop_column("brand_books", "brand_archetype")
    op.drop_column("brand_books", "brand_story")
    op.drop_column("brand_books", "core_values")
    op.drop_column("brand_books", "audience_exclusions")
    op.drop_column("brand_books", "vision")

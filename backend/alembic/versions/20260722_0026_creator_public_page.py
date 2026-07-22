"""public creator page + QR sharing

Phase 6 — a separate, explicit opt-in from `discoverable`: a no-login page on
the open internet, with a per-field visibility allow-list the creator
controls, plus a view counter for the "X people have checked out your page"
loop on /portal.

Revision ID: b2f6e9c14a75
Revises: c4b9d271e853
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2f6e9c14a75"
down_revision: str | None = "c4b9d271e853"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("creators", sa.Column("public_page_enabled", sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
    op.add_column("creators", sa.Column("public_slug", sa.String(140), nullable=True))
    op.add_column("creators", sa.Column("public_fields", sa.JSON(), nullable=False,
                                        server_default=sa.text("'[]'::json")))
    op.add_column("creators", sa.Column("public_view_count", sa.Integer(), nullable=False,
                                        server_default="0"))
    op.add_column("creators", sa.Column("public_last_viewed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_creators_public_page_enabled", "creators", ["public_page_enabled"])
    op.create_index("ix_creators_public_slug", "creators", ["public_slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_creators_public_slug", table_name="creators")
    op.drop_index("ix_creators_public_page_enabled", table_name="creators")
    op.drop_column("creators", "public_last_viewed_at")
    op.drop_column("creators", "public_view_count")
    op.drop_column("creators", "public_fields")
    op.drop_column("creators", "public_slug")
    op.drop_column("creators", "public_page_enabled")

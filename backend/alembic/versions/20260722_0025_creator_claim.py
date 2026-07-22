"""creator portal groundwork: claim fields

Phase 6 — lets a self-service user verify themselves against an existing
agency-managed Creator record via a signed invite, without transferring
tenant ownership.

Revision ID: c4b9d271e853
Revises: a71c5e9b3f02
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4b9d271e853"
down_revision: str | None = "a71c5e9b3f02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("creators", sa.Column("claimed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("creators", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_creators_claimed_by_user_id", "creators", "admin_users",
                          ["claimed_by_user_id"], ["id"])
    op.create_index("ix_creators_claimed_by_user_id", "creators", ["claimed_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_creators_claimed_by_user_id", table_name="creators")
    op.drop_constraint("fk_creators_claimed_by_user_id", "creators", type_="foreignkey")
    op.drop_column("creators", "claimed_at")
    op.drop_column("creators", "claimed_by_user_id")

"""account auto-approve autopilot columns (P3-M7)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-04 18:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("auto_approve_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("accounts", sa.Column("auto_approve_until", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("auto_approve_set_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_accounts_auto_approve_set_by",
        "accounts", "admin_users",
        ["auto_approve_set_by"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_accounts_auto_approve_set_by", "accounts", type_="foreignkey")
    op.drop_column("accounts", "auto_approve_set_by")
    op.drop_column("accounts", "auto_approve_until")
    op.drop_column("accounts", "auto_approve_enabled")

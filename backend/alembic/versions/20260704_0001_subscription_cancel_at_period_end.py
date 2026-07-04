"""subscription cancel_at_period_end

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-04 00:01:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "cancel_at_period_end")

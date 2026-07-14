"""brand: industry field for onboarding personalization

Revision ID: b7d19f0a3c2e
Revises: f2a3b4c5d6e7
Create Date: 2026-07-14 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d19f0a3c2e"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("industry", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("brands", "industry")

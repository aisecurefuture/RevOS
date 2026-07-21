"""match_products: discoverable opt-in (symmetric with creators)

Revision ID: a4d81f6c2b95
Revises: f3c9a5710e28
Create Date: 2026-07-21 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4d81f6c2b95"
down_revision: str | None = "f3c9a5710e28"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("match_products", sa.Column("discoverable", sa.Boolean(), nullable=False,
                                              server_default=sa.false()))
    op.add_column("match_products", sa.Column("discoverable_at", sa.DateTime(), nullable=True))
    op.create_index("ix_match_products_discoverable", "match_products", ["discoverable"])


def downgrade() -> None:
    op.drop_index("ix_match_products_discoverable", table_name="match_products")
    op.drop_column("match_products", "discoverable_at")
    op.drop_column("match_products", "discoverable")

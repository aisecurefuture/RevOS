"""industry_benchmarks: preserve verbatim source industry label (bugfix)

industry_category rolls a report's industry segment up into one of 11 broad
cohort buckets, which is lossy by design (e.g. "Veterinary Services" rolls up
to "healthcare", and anything that doesn't fit any bucket rolled up to
"other" with the real name discarded entirely). industry_label stores the
report's original text so nothing is lost even when the rollup is coarse.

Revision ID: e19a3d5f7c02
Revises: d84f2a6c93b1
Create Date: 2026-07-22 00:05:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e19a3d5f7c02"
down_revision: str | None = "d84f2a6c93b1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("industry_benchmarks", sa.Column("industry_label", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("industry_benchmarks", "industry_label")

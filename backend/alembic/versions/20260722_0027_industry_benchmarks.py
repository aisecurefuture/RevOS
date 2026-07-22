"""third-party industry benchmarks (BM1)

Admin-curated fallback for when RevOS's own cohort benchmarks are too thin —
figures read off published reports (Rival IQ/Quid, Socialinsider), not a live
paid API. Platform-wide reference data, not tenant-scoped.

Revision ID: d84f2a6c93b1
Revises: b2f6e9c14a75
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d84f2a6c93b1"
down_revision: str | None = "b2f6e9c14a75"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "industry_benchmarks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("industry_category", sa.String(40), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default="all"),
        sa.Column("metric", sa.String(40), nullable=False, server_default="engagement_rate"),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("period_label", sa.String(40), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("industry_category", "platform", "metric", "period_label",
                            name="uq_benchmark_figure"),
    )
    op.create_index("ix_industry_benchmarks_industry_category", "industry_benchmarks", ["industry_category"])
    op.create_index("ix_industry_benchmarks_platform", "industry_benchmarks", ["platform"])
    op.create_index("ix_industry_benchmarks_metric", "industry_benchmarks", ["metric"])


def downgrade() -> None:
    op.drop_table("industry_benchmarks")

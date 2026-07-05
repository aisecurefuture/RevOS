"""content autopilot config (P3)

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-07-05 18:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "autopilot_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("platforms", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("posts_per_run", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("run_interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("content_themes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("default_cta", sa.String(300), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("configured_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["configured_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", name="uq_autopilot_config_brand"),
    )
    op.create_index("ix_autopilot_configs_account_id", "autopilot_configs", ["account_id"])
    op.create_index("ix_autopilot_configs_brand_id", "autopilot_configs", ["brand_id"])
    op.create_index("ix_autopilot_configs_enabled", "autopilot_configs", ["enabled"])
    op.create_index("ix_autopilot_configs_deleted_at", "autopilot_configs", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("autopilot_configs")

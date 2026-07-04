"""social_connections table + social_posts.social_connection_id (M5)

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-04 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("handle", sa.String(200), nullable=True),
        sa.Column("display_name", sa.String(300), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("token_ref", sa.String(500), nullable=False),
        sa.Column("connected_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("platform_meta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connected_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_connections_account_id", "social_connections", ["account_id"])
    op.create_index("ix_social_connections_platform", "social_connections", ["platform"])
    op.create_index("ix_social_connections_external_id", "social_connections", ["external_id"])
    op.create_index("ix_social_connections_status", "social_connections", ["status"])
    op.create_index("ix_social_connections_connected_by", "social_connections", ["connected_by"])
    op.create_index("ix_social_connections_deleted_at", "social_connections", ["deleted_at"])

    op.add_column(
        "social_posts",
        sa.Column("social_connection_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_social_posts_social_connection_id",
        "social_posts",
        "social_connections",
        ["social_connection_id"],
        ["id"],
    )
    op.create_index(
        "ix_social_posts_social_connection_id",
        "social_posts",
        ["social_connection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_social_posts_social_connection_id", table_name="social_posts")
    op.drop_constraint("fk_social_posts_social_connection_id", "social_posts", type_="foreignkey")
    op.drop_column("social_posts", "social_connection_id")

    op.drop_index("ix_social_connections_deleted_at", table_name="social_connections")
    op.drop_index("ix_social_connections_connected_by", table_name="social_connections")
    op.drop_index("ix_social_connections_status", table_name="social_connections")
    op.drop_index("ix_social_connections_external_id", table_name="social_connections")
    op.drop_index("ix_social_connections_platform", table_name="social_connections")
    op.drop_index("ix_social_connections_account_id", table_name="social_connections")
    op.drop_table("social_connections")

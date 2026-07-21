"""social comment inbox + approval-gated replies

Revision ID: a1c8e04f7b62
Revises: 9c4e7f2a5d18
Create Date: 2026-07-20 21:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c8e04f7b62"
down_revision: str | None = "9c4e7f2a5d18"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "social_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("external_post_id", sa.String(200), nullable=False),
        sa.Column("external_comment_id", sa.String(200), nullable=False),
        sa.Column("permalink", sa.String(600), nullable=True),
        sa.Column("author_name", sa.String(200), nullable=True),
        sa.Column("author_external_id", sa.String(200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("relevance_note", sa.String(300), nullable=True),
        sa.Column("drafted_reply", sa.Text(), nullable=True),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("reply_external_id", sa.String(200), nullable=True),
        sa.Column("liked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["social_connections.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_comment_id", name="uq_social_comment_external"),
    )
    op.create_index("ix_social_comments_account_id", "social_comments", ["account_id"])
    op.create_index("ix_social_comments_connection_id", "social_comments", ["connection_id"])
    op.create_index("ix_social_comments_brand_id", "social_comments", ["brand_id"])
    op.create_index("ix_social_comments_platform", "social_comments", ["platform"])
    op.create_index("ix_social_comments_external_comment_id", "social_comments", ["external_comment_id"])
    op.create_index("ix_social_comments_status", "social_comments", ["status"])
    op.create_index("ix_social_comments_approval_id", "social_comments", ["approval_id"])
    op.create_index("ix_social_comments_deleted_at", "social_comments", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("social_comments")

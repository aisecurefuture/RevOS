"""collaboration assets: versioned shared content + comments + two-sided approval

CW2 — shared assets + review-before-post:
- collaboration_assets / _versions / _comments / _approvals
All cross-tenant (plain BaseModel, not tenant-scoped), same pattern as
Collaboration/CollaborationShare.

Revision ID: e9f3b81d47a6
Revises: d1a7c93e60f4
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e9f3b81d47a6"
down_revision: str | None = "d1a7c93e60f4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collaboration_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(250), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("linked_social_post_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_id"], ["collaborations.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("collaboration_id", "created_by_account_id", "kind", "state",
                "linked_social_post_id"):
        op.create_index(f"ix_collaboration_assets_{col}", "collaboration_assets", [col])

    op.create_table(
        "collaboration_asset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("media_urls", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["collaboration_assets.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "version", name="uq_asset_version"),
    )
    op.create_index("ix_collaboration_asset_versions_asset_id", "collaboration_asset_versions", ["asset_id"])
    op.create_index("ix_collaboration_asset_versions_version", "collaboration_asset_versions", ["version"])
    op.create_index("ix_collaboration_asset_versions_created_by_account_id",
                    "collaboration_asset_versions", ["created_by_account_id"])

    op.create_table(
        "collaboration_asset_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("author_account_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["collaboration_assets.id"]),
        sa.ForeignKeyConstraint(["author_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collaboration_asset_comments_asset_id", "collaboration_asset_comments", ["asset_id"])
    op.create_index("ix_collaboration_asset_comments_author_account_id",
                    "collaboration_asset_comments", ["author_account_id"])

    op.create_table(
        "collaboration_asset_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["collaboration_assets.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "version", "account_id", name="uq_asset_approval_party"),
    )
    op.create_index("ix_collaboration_asset_approvals_asset_id", "collaboration_asset_approvals", ["asset_id"])
    op.create_index("ix_collaboration_asset_approvals_version", "collaboration_asset_approvals", ["version"])
    op.create_index("ix_collaboration_asset_approvals_account_id", "collaboration_asset_approvals", ["account_id"])


def downgrade() -> None:
    op.drop_table("collaboration_asset_approvals")
    op.drop_table("collaboration_asset_comments")
    op.drop_table("collaboration_asset_versions")
    op.drop_table("collaboration_assets")

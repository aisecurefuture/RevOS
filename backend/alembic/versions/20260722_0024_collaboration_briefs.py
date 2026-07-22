"""collaboration briefs + deliverables: goals, disclosure, usage rights, milestones

CW3 — briefs, deliverables, disclosure:
- collaboration_briefs: 1:1 co-authored brief per collaboration, carrying FTC
  disclosure requirements + usage/licensing terms agreed up front.
- collaboration_deliverables: milestone list tracked to completion, optionally
  linked to the CollaborationAsset that fulfills it.
Both cross-tenant (plain BaseModel, not tenant-scoped), same pattern as the
rest of the collaboration workspace.

Revision ID: f4a08c2e91b7
Revises: e9f3b81d47a6
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a08c2e91b7"
down_revision: str | None = "e9f3b81d47a6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collaboration_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column("key_messages", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("dos", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("donts", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("requires_disclosure", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("disclosure_text", sa.String(200), nullable=True),
        sa.Column("usage_rights", sa.Text(), nullable=True),
        sa.Column("usage_duration_days", sa.Integer(), nullable=True),
        sa.Column("whitelisting_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("boost_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_id"], ["collaborations.id"]),
        sa.ForeignKeyConstraint(["updated_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collaboration_id", name="uq_collaboration_brief"),
    )
    op.create_index("ix_collaboration_briefs_collaboration_id", "collaboration_briefs", ["collaboration_id"])

    op.create_table(
        "collaboration_deliverables",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_id"], ["collaborations.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["collaboration_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("collaboration_id", "created_by_account_id", "due_at", "status", "asset_id"):
        op.create_index(f"ix_collaboration_deliverables_{col}", "collaboration_deliverables", [col])


def downgrade() -> None:
    op.drop_table("collaboration_deliverables")
    op.drop_table("collaboration_briefs")

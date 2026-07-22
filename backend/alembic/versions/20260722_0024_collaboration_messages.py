"""collaboration messages: full threads with report

Phase 6 — full messaging threads within an accepted collaboration, unlocked
after the pre-accept single-message stage (CollaborationRequest.message).
"Block" reuses the existing end_collaboration action; "report" flags a message
for platform-admin review.

Revision ID: a71c5e9b3f02
Revises: f4a08c2e91b7
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a71c5e9b3f02"
down_revision: str | None = "f4a08c2e91b7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collaboration_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_id", sa.Uuid(), nullable=False),
        sa.Column("sender_account_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("is_flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("flagged_by_account_id", sa.Uuid(), nullable=True),
        sa.Column("flagged_reason", sa.String(500), nullable=True),
        sa.Column("flagged_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_id"], ["collaborations.id"]),
        sa.ForeignKeyConstraint(["sender_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["sender_user_id"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["flagged_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("collaboration_id", "sender_account_id", "sender_user_id", "is_flagged"):
        op.create_index(f"ix_collaboration_messages_{col}", "collaboration_messages", [col])


def downgrade() -> None:
    op.drop_table("collaboration_messages")

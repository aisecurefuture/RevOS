"""viral video scripts (P3-M4)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-06 01:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_scripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("persona_identity_id", sa.Uuid(), nullable=True),
        sa.Column("target_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("angle", sa.String(500), nullable=True),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("hook", sa.String(500), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed_gate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gate", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["persona_identity_id"], ["persona_identities.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_scripts_account_id", "video_scripts", ["account_id"])
    op.create_index("ix_video_scripts_brand_id", "video_scripts", ["brand_id"])
    op.create_index("ix_video_scripts_persona_identity_id", "video_scripts", ["persona_identity_id"])
    op.create_index("ix_video_scripts_passed_gate", "video_scripts", ["passed_gate"])
    op.create_index("ix_video_scripts_created_by", "video_scripts", ["created_by"])
    op.create_index("ix_video_scripts_deleted_at", "video_scripts", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("video_scripts")

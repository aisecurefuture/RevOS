"""email login codes (anti-bot login step)

Revision ID: d5f28a1b6c94
Revises: c4e91a7b3f28
Create Date: 2026-07-14 18:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f28a1b6c94"
down_revision: str | None = "c4e91a7b3f28"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_login_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_login_codes_user_id", "email_login_codes", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_login_codes")

"""invitations table + email_verified_at (Phase 2 M2)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-03 23:45:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "invitations",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(length=320), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "email", name="uq_invitation_account_email"),
    )
    op.create_index(op.f("ix_invitations_id"), "invitations", ["id"])
    op.create_index(op.f("ix_invitations_account_id"), "invitations", ["account_id"])
    op.create_index(op.f("ix_invitations_email"), "invitations", ["email"])
    op.create_index(op.f("ix_invitations_deleted_at"), "invitations", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("invitations")
    op.drop_column("admin_users", "email_verified_at")

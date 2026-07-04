"""optional TOTP 2FA (Phase 2 M2)

Adds TOTP fields to admin_users and a recovery_codes table.

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-03 23:30:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "admin_users",
        sa.Column("totp_secret_enc", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    )
    op.add_column("admin_users", sa.Column("totp_confirmed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "recovery_codes",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recovery_codes_id"), "recovery_codes", ["id"])
    op.create_index(op.f("ix_recovery_codes_user_id"), "recovery_codes", ["user_id"])
    op.create_index(op.f("ix_recovery_codes_code_hash"), "recovery_codes", ["code_hash"])
    op.create_index(op.f("ix_recovery_codes_deleted_at"), "recovery_codes", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("recovery_codes")
    op.drop_column("admin_users", "totp_confirmed_at")
    op.drop_column("admin_users", "totp_secret_enc")
    op.drop_column("admin_users", "totp_enabled")

"""platform admin: account disable + user login-lockout fields

Revision ID: c4e91a7b3f28
Revises: b7d19f0a3c2e
Create Date: 2026-07-14 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e91a7b3f28"
down_revision: str | None = "b7d19f0a3c2e"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("disabled_at", sa.DateTime(), nullable=True))
    op.add_column("accounts", sa.Column("disabled_by", sa.Uuid(), nullable=True))
    op.add_column("accounts", sa.Column("disabled_reason", sa.String(300), nullable=True))
    op.create_foreign_key(
        "fk_accounts_disabled_by", "accounts", "admin_users", ["disabled_by"], ["id"]
    )
    op.add_column(
        "admin_users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("admin_users", sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("admin_users", "locked_until")
    op.drop_column("admin_users", "failed_login_count")
    op.drop_constraint("fk_accounts_disabled_by", "accounts", type_="foreignkey")
    op.drop_column("accounts", "disabled_reason")
    op.drop_column("accounts", "disabled_by")
    op.drop_column("accounts", "disabled_at")

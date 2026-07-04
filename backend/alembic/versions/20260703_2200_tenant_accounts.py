"""tenant accounts + isolation (Phase 2 M1)

Adds accounts + memberships, an account_id on every tenant table, and backfills
existing (single-org) data into the owner's personal account.

Revision ID: c1a2b3d4e5f6
Revises: 689231f99eca
Create Date: 2026-07-03 22:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "689231f99eca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table whose model inherits TenantModel (carries account_id).
TENANT_TABLES = [
    "ab_tests", "approval_requests", "audiences", "brand_voices", "brands",
    "buyer_personas", "campaigns", "companies", "consent_records", "contacts",
    "content_calendars", "content_items", "conversion_goals", "ctas", "deals",
    "email_messages", "email_templates", "enrollments", "events",
    "form_submissions", "forms", "hashtags", "hooks", "landing_pages",
    "lead_tags", "leads", "media_assets", "media_variants", "notes", "offers",
    "pillars", "pipeline_stages", "revenue_goals", "revenue_records", "segments",
    "sender_identities", "sequence_steps", "sequences", "social_accounts",
    "social_campaigns", "social_posts", "step_runs", "suppressions", "tags",
    "tasks", "utm_captures", "utm_links",
]

# The owner's personal account: home for all pre-existing (single-org) data.
_OWNER_ACCOUNT = (
    "(SELECT a.id FROM accounts a JOIN admin_users u ON u.id = a.owner_user_id "
    "WHERE u.role = 'owner' ORDER BY u.created_at LIMIT 1)"
)


def _timestamps() -> list:
    return [
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
    ]


def upgrade() -> None:
    # --- 1. accounts -------------------------------------------------------
    op.create_table(
        "accounts",
        *_timestamps(),
        sa.Column("type", sqlmodel.sql.sqltypes.AutoString(length=12), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(length=140), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_accounts_id"), "accounts", ["id"])
    op.create_index(op.f("ix_accounts_type"), "accounts", ["type"])
    op.create_index(op.f("ix_accounts_slug"), "accounts", ["slug"])
    op.create_index(op.f("ix_accounts_owner_user_id"), "accounts", ["owner_user_id"])
    op.create_index(op.f("ix_accounts_deleted_at"), "accounts", ["deleted_at"])

    # --- 2. memberships ----------------------------------------------------
    op.create_table(
        "memberships",
        *_timestamps(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "account_id", name="uq_membership_user_account"),
    )
    op.create_index(op.f("ix_memberships_id"), "memberships", ["id"])
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"])
    op.create_index(op.f("ix_memberships_account_id"), "memberships", ["account_id"])
    op.create_index(op.f("ix_memberships_deleted_at"), "memberships", ["deleted_at"])

    # --- 3. account_id on every tenant table (nullable; backfilled below) --
    for t in TENANT_TABLES:
        op.add_column(t, sa.Column("account_id", sa.Uuid(), nullable=True))
        op.create_index(op.f(f"ix_{t}_account_id"), t, ["account_id"])
        op.create_foreign_key(f"fk_{t}_account_id", t, "accounts", ["account_id"], ["id"])

    # --- 4. backfill (Postgres) --------------------------------------------
    # a) a personal account for every existing user
    op.execute(
        "INSERT INTO accounts (id, created_at, updated_at, type, name, slug, owner_user_id) "
        "SELECT gen_random_uuid(), now(), now(), 'personal', "
        "COALESCE(NULLIF(u.full_name, ''), split_part(u.email, '@', 1)), "
        "'user-' || substr(u.id::text, 1, 8), u.id "
        "FROM admin_users u "
        "WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.user_id = u.id)"
    )
    # b) owner membership for each new personal account (role = the user's role)
    op.execute(
        "INSERT INTO memberships (id, created_at, updated_at, user_id, account_id, role) "
        "SELECT gen_random_uuid(), now(), now(), a.owner_user_id, a.id, u.role "
        "FROM accounts a JOIN admin_users u ON u.id = a.owner_user_id "
        "WHERE NOT EXISTS (SELECT 1 FROM memberships m "
        "WHERE m.user_id = a.owner_user_id AND m.account_id = a.id)"
    )
    # c) preserve shared access: non-owner users also join the owner's account
    op.execute(
        "INSERT INTO memberships (id, created_at, updated_at, user_id, account_id, role) "
        f"SELECT gen_random_uuid(), now(), now(), u.id, {_OWNER_ACCOUNT}, u.role "
        "FROM admin_users u "
        f"WHERE u.role <> 'owner' AND {_OWNER_ACCOUNT} IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM memberships m "
        f"WHERE m.user_id = u.id AND m.account_id = {_OWNER_ACCOUNT})"
    )
    # d) all existing (single-org) tenant rows belong to the owner's account
    for t in TENANT_TABLES:
        op.execute(
            f"UPDATE {t} SET account_id = {_OWNER_ACCOUNT} WHERE account_id IS NULL"
        )


def downgrade() -> None:
    for t in TENANT_TABLES:
        op.drop_constraint(f"fk_{t}_account_id", t, type_="foreignkey")
        op.drop_index(op.f(f"ix_{t}_account_id"), table_name=t)
        op.drop_column(t, "account_id")
    op.drop_table("memberships")
    op.drop_table("accounts")

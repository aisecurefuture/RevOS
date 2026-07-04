"""subscriptions table (Phase 2 M3)

Creates the subscriptions table and backfills a trialing subscription for
every existing account.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-04 00:00:00.000000+00:00
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIAL_DAYS = 14


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False,
                  server_default="trial"),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False,
                  server_default="trialing"),
        sa.Column("trial_ends_at", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("stripe_customer_id", sqlmodel.sql.sqltypes.AutoString(length=100),
                  nullable=True),
        sa.Column("stripe_subscription_id", sqlmodel.sql.sqltypes.AutoString(length=100),
                  nullable=True),
        sa.Column("stripe_price_id", sqlmodel.sql.sqltypes.AutoString(length=100),
                  nullable=True),
        sa.Column("billing_interval", sqlmodel.sql.sqltypes.AutoString(length=10),
                  nullable=True),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_subscriptions_account_id"),
    )
    op.create_index(op.f("ix_subscriptions_id"), "subscriptions", ["id"])
    op.create_index(op.f("ix_subscriptions_account_id"), "subscriptions", ["account_id"])
    op.create_index(op.f("ix_subscriptions_plan"), "subscriptions", ["plan"])
    op.create_index(op.f("ix_subscriptions_status"), "subscriptions", ["status"])
    op.create_index(op.f("ix_subscriptions_stripe_customer_id"),
                    "subscriptions", ["stripe_customer_id"])
    op.create_index(op.f("ix_subscriptions_stripe_subscription_id"),
                    "subscriptions", ["stripe_subscription_id"])
    op.create_index(op.f("ix_subscriptions_deleted_at"), "subscriptions", ["deleted_at"])

    # Backfill: every existing account gets a 14-day trial starting from now.
    now = datetime.utcnow()
    trial_end = now + timedelta(days=_TRIAL_DAYS)
    conn = op.get_bind()
    accounts = conn.execute(sa.text("SELECT id FROM accounts WHERE deleted_at IS NULL")).fetchall()
    import uuid as _uuid
    for (account_id,) in accounts:
        conn.execute(
            sa.text(
                "INSERT INTO subscriptions "
                "(id, account_id, plan, status, trial_ends_at, created_at, updated_at) "
                "VALUES (:id, :account_id, 'trial', 'trialing', :trial_end, :now, :now)"
            ),
            {"id": str(_uuid.uuid4()), "account_id": str(account_id),
             "trial_end": trial_end, "now": now},
        )


def downgrade() -> None:
    op.drop_table("subscriptions")

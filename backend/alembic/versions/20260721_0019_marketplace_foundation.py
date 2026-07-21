"""marketplace foundation: creator discoverability + collaboration requests

MK1 — the two-sided marketplace foundation:
- creators.discoverable / discoverable_at (opt-in cross-tenant visibility)
- collaboration_requests: structured outreach either side may initiate. NOT
  tenant-scoped — carries explicit initiator/recipient account columns.

Revision ID: f3c9a5710e28
Revises: e2b6d3149c07
Create Date: 2026-07-21 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3c9a5710e28"
down_revision: str | None = "e2b6d3149c07"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("creators", sa.Column("discoverable", sa.Boolean(), nullable=False,
                                        server_default=sa.false()))
    op.add_column("creators", sa.Column("discoverable_at", sa.DateTime(), nullable=True))
    op.create_index("ix_creators_discoverable", "creators", ["discoverable"])

    op.create_table(
        "collaboration_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("initiator_account_id", sa.Uuid(), nullable=False),
        sa.Column("initiator_user_id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_account_id", sa.Uuid(), nullable=True),
        sa.Column("message", sa.String(2000), nullable=False),
        sa.Column("response_note", sa.String(2000), nullable=True),
        sa.Column("response_channel", sa.String(16), nullable=True),
        sa.Column("brokered_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["initiator_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["initiator_user_id"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["match_products.id"]),
        sa.ForeignKeyConstraint(["recipient_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["brokered_by_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("direction", "status", "initiator_account_id", "initiator_user_id",
                "creator_id", "product_id", "recipient_account_id",
                "brokered_by_user_id", "expires_at"):
        op.create_index(f"ix_collaboration_requests_{col}", "collaboration_requests", [col])


def downgrade() -> None:
    op.drop_table("collaboration_requests")
    op.drop_index("ix_creators_discoverable", table_name="creators")
    op.drop_column("creators", "discoverable_at")
    op.drop_column("creators", "discoverable")

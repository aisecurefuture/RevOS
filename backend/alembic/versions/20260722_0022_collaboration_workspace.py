"""collaboration workspace: creators.brand_id + collaborations + shares

CW1 — the collaboration workspace foundation:
- creators.brand_id (reuse a Brand's Brand Book instead of a parallel book)
- collaborations (spawned from an accepted request; cross-tenant, NOT scoped)
- collaboration_shares (consent-gated, time-boxed knowledge sharing)

Revision ID: d1a7c93e60f4
Revises: b8e2f47a1c93
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1a7c93e60f4"
down_revision: str | None = "b8e2f47a1c93"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("creators", sa.Column("brand_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_creators_brand_id", "creators", "brands", ["brand_id"], ["id"])
    op.create_index("ix_creators_brand_id", "creators", ["brand_id"])

    op.create_table(
        "collaborations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_request_id", sa.Uuid(), nullable=False),
        sa.Column("brand_account_id", sa.Uuid(), nullable=False),
        sa.Column("creator_account_id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="one_off"),
        sa.Column("state", sa.String(16), nullable=False, server_default="active"),
        sa.Column("title", sa.String(250), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_request_id"], ["collaboration_requests.id"]),
        sa.ForeignKeyConstraint(["brand_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["creator_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["match_products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collaboration_request_id", name="uq_collaboration_request"),
    )
    for col in ("collaboration_request_id", "brand_account_id", "creator_account_id",
                "creator_id", "product_id", "kind", "state"):
        op.create_index(f"ix_collaborations_{col}", "collaborations", [col])

    op.create_table(
        "collaboration_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_id", sa.Uuid(), nullable=False),
        sa.Column("shared_by_account_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(200), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_id"], ["collaborations.id"]),
        sa.ForeignKeyConstraint(["shared_by_account_id"], ["accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collaboration_id", "resource_type", "resource_id",
                            "shared_by_account_id", name="uq_collab_share_resource"),
    )
    for col in ("collaboration_id", "shared_by_account_id", "resource_type",
                "resource_id", "expires_at", "status"):
        op.create_index(f"ix_collaboration_shares_{col}", "collaboration_shares", [col])


def downgrade() -> None:
    op.drop_table("collaboration_shares")
    op.drop_table("collaborations")
    op.drop_index("ix_creators_brand_id", table_name="creators")
    op.drop_constraint("fk_creators_brand_id", "creators", type_="foreignkey")
    op.drop_column("creators", "brand_id")

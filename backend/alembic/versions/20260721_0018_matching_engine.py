"""matching engine: creators, creator_managers, match_products

Adds the Creator↔Product matching data model (Phase 3, M1):
- creators (tenant-owned; one-to-many with social_connections via creator_id)
- creator_managers (M2M creator↔user for agency/team co-management)
- match_products (sponsorable products creators are ranked against)
- social_connections.creator_id (nullable FK; NULL = the tenant's own accounts)

Revision ID: e2b6d3149c07
Revises: c7f1a9e26b04
Create Date: 2026-07-21 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2b6d3149c07"
down_revision: str | None = "c7f1a9e26b04"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "creators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("handle", sa.String(200), nullable=True),
        sa.Column("primary_platform", sa.String(20), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(80), nullable=True),
        sa.Column("industries", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("size_tier", sa.String(16), nullable=True),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("location", sa.String(160), nullable=True),
        sa.Column("management", sa.String(20), nullable=False, server_default="self_managed"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("follower_count", sa.Integer(), nullable=True),
        sa.Column("engagement_rate", sa.Float(), nullable=True),
        sa.Column("avg_views", sa.Integer(), nullable=True),
        sa.Column("demographics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("audience_source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("audience_captured_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.String(5000), nullable=True),
        sa.Column("contact_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_creators_account_id", "creators", ["account_id"])
    op.create_index("ix_creators_display_name", "creators", ["display_name"])
    op.create_index("ix_creators_industry", "creators", ["industry"])
    op.create_index("ix_creators_size_tier", "creators", ["size_tier"])
    op.create_index("ix_creators_category", "creators", ["category"])
    op.create_index("ix_creators_management", "creators", ["management"])
    op.create_index("ix_creators_status", "creators", ["status"])
    op.create_index("ix_creators_contact_id", "creators", ["contact_id"])
    op.create_index("ix_creators_deleted_at", "creators", ["deleted_at"])

    op.create_table(
        "creator_managers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("creator_id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("creator_id", "admin_user_id", name="uq_creator_manager"),
    )
    op.create_index("ix_creator_managers_account_id", "creator_managers", ["account_id"])
    op.create_index("ix_creator_managers_creator_id", "creator_managers", ["creator_id"])
    op.create_index("ix_creator_managers_admin_user_id", "creator_managers", ["admin_user_id"])
    op.create_index("ix_creator_managers_deleted_at", "creator_managers", ["deleted_at"])

    op.create_table(
        "match_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(250), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("industry", sa.String(80), nullable=True),
        sa.Column("industries", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("target_audience", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("budget_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("offer_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_products_account_id", "match_products", ["account_id"])
    op.create_index("ix_match_products_brand_id", "match_products", ["brand_id"])
    op.create_index("ix_match_products_name", "match_products", ["name"])
    op.create_index("ix_match_products_category", "match_products", ["category"])
    op.create_index("ix_match_products_industry", "match_products", ["industry"])
    op.create_index("ix_match_products_status", "match_products", ["status"])
    op.create_index("ix_match_products_offer_id", "match_products", ["offer_id"])
    op.create_index("ix_match_products_deleted_at", "match_products", ["deleted_at"])

    op.add_column("social_connections", sa.Column("creator_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_social_connections_creator_id", "social_connections", "creators",
        ["creator_id"], ["id"],
    )
    op.create_index("ix_social_connections_creator_id", "social_connections", ["creator_id"])


def downgrade() -> None:
    op.drop_index("ix_social_connections_creator_id", table_name="social_connections")
    op.drop_constraint("fk_social_connections_creator_id", "social_connections", type_="foreignkey")
    op.drop_column("social_connections", "creator_id")
    op.drop_table("match_products")
    op.drop_table("creator_managers")
    op.drop_table("creators")

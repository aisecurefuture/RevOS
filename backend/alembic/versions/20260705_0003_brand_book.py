"""brand book: grounding record, claims, facts (P3-M1)

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-05 15:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brand_books",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("mission", sa.Text(), nullable=True),
        sa.Column("positioning", sa.Text(), nullable=True),
        sa.Column("elevator_pitch", sa.Text(), nullable=True),
        sa.Column("target_summary", sa.Text(), nullable=True),
        sa.Column("key_messages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("banned_terms", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("required_disclaimers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("compliance_notes", sa.Text(), nullable=True),
        sa.Column("competitors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", name="uq_brand_book_brand"),
    )
    op.create_index("ix_brand_books_account_id", "brand_books", ["account_id"])
    op.create_index("ix_brand_books_brand_id", "brand_books", ["brand_id"])
    op.create_index("ix_brand_books_is_published", "brand_books", ["is_published"])
    op.create_index("ix_brand_books_deleted_at", "brand_books", ["deleted_at"])

    op.create_table(
        "brand_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("claim", sa.String(500), nullable=False),
        sa.Column("proof", sa.Text(), nullable=True),
        sa.Column("category", sa.String(16), nullable=False, server_default="other"),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brand_claims_account_id", "brand_claims", ["account_id"])
    op.create_index("ix_brand_claims_brand_id", "brand_claims", ["brand_id"])
    op.create_index("ix_brand_claims_approved", "brand_claims", ["approved"])
    op.create_index("ix_brand_claims_created_by", "brand_claims", ["created_by"])
    op.create_index("ix_brand_claims_deleted_at", "brand_claims", ["deleted_at"])

    op.create_table(
        "brand_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(300), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("source", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brand_facts_account_id", "brand_facts", ["account_id"])
    op.create_index("ix_brand_facts_brand_id", "brand_facts", ["brand_id"])
    op.create_index("ix_brand_facts_created_by", "brand_facts", ["created_by"])
    op.create_index("ix_brand_facts_deleted_at", "brand_facts", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("brand_facts")
    op.drop_table("brand_claims")
    op.drop_table("brand_books")

"""reputation: certifications + reviews

RK1 — verifiable trust signals feeding the future brand/product rating engine:
- certifications: polymorphic (creator | match_product), platform-admin
  verifiable, tenant-owned like the subject it's attached to.
- reviews: feedback tied to a real, completed collaboration_request. NOT
  tenant-scoped — the reviewer and subject are different tenants.

Revision ID: b8e2f47a1c93
Revises: a4d81f6c2b95
Create Date: 2026-07-22 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e2f47a1c93"
down_revision: str | None = "a4d81f6c2b95"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "certifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("subject_type", sa.String(20), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("issuer", sa.String(200), nullable=True),
        sa.Column("certificate_number", sa.String(120), nullable=True),
        sa.Column("verification_url", sa.String(500), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verified_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("account_id", "subject_type", "subject_id", "expires_at", "status", "verified"):
        op.create_index(f"ix_certifications_{col}", "certifications", [col])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collaboration_request_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(24), nullable=False),
        sa.Column("reviewer_account_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("subject_creator_id", sa.Uuid(), nullable=True),
        sa.Column("subject_product_id", sa.Uuid(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("dimension_ratings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("comment", sa.String(2000), nullable=True),
        sa.Column("response", sa.String(2000), nullable=True),
        sa.Column("response_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["collaboration_request_id"], ["collaboration_requests.id"]),
        sa.ForeignKeyConstraint(["reviewer_account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["subject_creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["subject_product_id"], ["match_products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating_range"),
        sa.UniqueConstraint("collaboration_request_id", "reviewer_account_id",
                            name="uq_review_collaboration_reviewer"),
    )
    for col in ("collaboration_request_id", "direction", "reviewer_account_id",
                "subject_creator_id", "subject_product_id"):
        op.create_index(f"ix_reviews_{col}", "reviews", [col])


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("certifications")

"""persona identity + consent (P3-M2)

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-05 21:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persona_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("buyer_persona_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("appearance_notes", sa.Text(), nullable=True),
        sa.Column("voice_notes", sa.Text(), nullable=True),
        sa.Column("training_video_path", sa.String(600), nullable=True),
        sa.Column("voice_sample_path", sa.String(600), nullable=True),
        sa.Column("reference_image_paths", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("voice_model_ref", sa.String(500), nullable=True),
        sa.Column("avatar_model_ref", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["buyer_persona_id"], ["buyer_personas.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_persona_identities_account_id", "persona_identities", ["account_id"])
    op.create_index("ix_persona_identities_brand_id", "persona_identities", ["brand_id"])
    op.create_index("ix_persona_identities_status", "persona_identities", ["status"])
    op.create_index("ix_persona_identities_created_by", "persona_identities", ["created_by"])
    op.create_index("ix_persona_identities_deleted_at", "persona_identities", ["deleted_at"])

    op.create_table(
        "persona_consents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("persona_identity_id", sa.Uuid(), nullable=False),
        sa.Column("subject_name", sa.String(200), nullable=False),
        sa.Column("subject_email", sa.String(320), nullable=False),
        sa.Column("consent_statement", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        sa.Column("granted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["persona_identity_id"], ["persona_identities.id"]),
        sa.ForeignKeyConstraint(["granted_by"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["admin_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_persona_consents_account_id", "persona_consents", ["account_id"])
    op.create_index("ix_persona_consents_persona_identity_id", "persona_consents", ["persona_identity_id"])
    op.create_index("ix_persona_consents_granted_by", "persona_consents", ["granted_by"])
    op.create_index("ix_persona_consents_is_active", "persona_consents", ["is_active"])
    op.create_index("ix_persona_consents_deleted_at", "persona_consents", ["deleted_at"])


def downgrade() -> None:
    op.drop_table("persona_consents")
    op.drop_table("persona_identities")

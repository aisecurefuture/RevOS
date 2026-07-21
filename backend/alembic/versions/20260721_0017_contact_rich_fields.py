"""contacts: notes, structured address, multi email/phone

Adds a notes field, structured mailing address, and JSON lists for multiple
emails/phones (each {value,label,is_primary}). The scalar email/phone columns
remain the authoritative primary.

Revision ID: c7f1a9e26b04
Revises: a1c8e04f7b62
Create Date: 2026-07-21 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7f1a9e26b04"
down_revision: str | None = "a1c8e04f7b62"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("emails", sa.JSON(), nullable=False,
                                        server_default=sa.text("'[]'::json")))
    op.add_column("contacts", sa.Column("phones", sa.JSON(), nullable=False,
                                        server_default=sa.text("'[]'::json")))
    op.add_column("contacts", sa.Column("address_line1", sa.String(length=200), nullable=True))
    op.add_column("contacts", sa.Column("address_line2", sa.String(length=200), nullable=True))
    op.add_column("contacts", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("contacts", sa.Column("region", sa.String(length=120), nullable=True))
    op.add_column("contacts", sa.Column("postal_code", sa.String(length=30), nullable=True))
    op.add_column("contacts", sa.Column("country", sa.String(length=80), nullable=True))
    op.add_column("contacts", sa.Column("notes", sa.String(length=5000), nullable=True))


def downgrade() -> None:
    for col in ("notes", "country", "postal_code", "region", "city",
                "address_line2", "address_line1", "phones", "emails"):
        op.drop_column("contacts", col)

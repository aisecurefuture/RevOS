"""Tenant accounts (workspaces) + per-account memberships (Phase 2 M1).

An **Account** is the unit of data isolation and (later) billing. Every user has
a personal account and may create/join team accounts. **Membership** grants a
user a role within an account; authorization is per-account, not global.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import BaseModel
from app.models.user import Role  # reuse owner > admin > editor > viewer


class AccountType(StrEnum):
    personal = "personal"   # auto-created per user
    team = "team"           # user-created, can invite members


class Account(BaseModel, table=True):
    __tablename__ = "accounts"

    type: AccountType = Field(
        default=AccountType.personal, sa_type=sa.String, max_length=12, index=True
    )
    name: str = Field(max_length=200)
    slug: str = Field(index=True, max_length=140)
    owner_user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)


class Membership(BaseModel, table=True):
    __tablename__ = "memberships"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "account_id", name="uq_membership_user_account"),
    )

    user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    role: Role = Field(default=Role.viewer, sa_type=sa.String, max_length=20)


class Invitation(BaseModel, table=True):
    """Pending invitation for a non-member to join an account (7-day signed link)."""

    __tablename__ = "invitations"
    __table_args__ = (
        sa.UniqueConstraint("account_id", "email", name="uq_invitation_account_email"),
    )

    account_id: uuid.UUID = Field(foreign_key="accounts.id", index=True)
    email: str = Field(max_length=320, index=True)
    role: Role = Field(default=Role.viewer, sa_type=sa.String, max_length=20)
    invited_by_user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    accepted_at: datetime | None = Field(default=None)

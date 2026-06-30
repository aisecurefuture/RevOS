"""Admin users, roles, audit log, API keys."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, BaseModel, utcnow


class Role(StrEnum):
    owner = "owner"      # full control incl. billing/integration secrets
    admin = "admin"      # manage everything except destructive owner actions
    editor = "editor"    # create/edit content + drafts; cannot send/approve
    viewer = "viewer"    # read-only dashboards


class AdminUser(BaseModel, table=True):
    __tablename__ = "admin_users"

    email: str = Field(unique=True, index=True, max_length=320)
    hashed_password: str = Field(max_length=255)
    full_name: str = Field(default="", max_length=200)
    role: Role = Field(default=Role.viewer, sa_type=sa.String, max_length=20)
    is_active: bool = Field(default=True)
    last_login_at: datetime | None = Field(default=None)
    # Bumped on password change / forced logout to invalidate all prior JWTs.
    token_version: int = Field(default=0)
    # MFA / future auth metadata (no secrets stored in plaintext).
    settings: dict = Field(default_factory=dict, sa_type=JSON)


class AuditLog(BaseModel, table=True):
    """Append-only record of privileged/admin actions (OWASP logging)."""

    __tablename__ = "audit_logs"

    user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)
    action: str = Field(index=True, max_length=120)         # e.g. "campaign.approve"
    entity_type: str | None = Field(default=None, max_length=80, index=True)
    entity_id: str | None = Field(default=None, max_length=80, index=True)
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=400)
    # Arbitrary structured detail (never contains secrets).
    meta: dict = Field(default_factory=dict, sa_type=JSON)


class ApiKey(BaseModel, table=True):
    """Hashed API keys for programmatic/webhook access (key shown once)."""

    __tablename__ = "api_keys"

    name: str = Field(max_length=120)
    prefix: str = Field(index=True, max_length=16)          # non-secret lookup hint
    hashed_key: str = Field(max_length=255)                 # store hash, never raw
    user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)
    scopes: list = Field(default_factory=list, sa_type=JSON)
    last_used_at: datetime | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > utcnow()

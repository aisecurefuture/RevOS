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
    # Brute-force lockout: failures accumulate; once locked, login is blocked
    # until locked_until passes (or a platform admin unlocks). Reset on success.
    failed_login_count: int = Field(default=0)
    locked_until: datetime | None = Field(default=None)
    # Bumped on password change / forced logout to invalidate all prior JWTs.
    token_version: int = Field(default=0)
    # Optional TOTP 2FA (Phase 2 M2). The secret is Fernet-encrypted at rest and
    # kept in Postgres (NOT OpenBao) so login never depends on Bao being unsealed.
    totp_enabled: bool = Field(default=False)
    totp_secret_enc: str | None = Field(default=None, max_length=255)
    totp_confirmed_at: datetime | None = Field(default=None)
    # Email verification (Phase 2 M2). Null = unverified.
    email_verified_at: datetime | None = Field(default=None)
    # Free-form auth/profile metadata (no secrets stored in plaintext).
    settings: dict = Field(default_factory=dict, sa_type=JSON)


class EmailLoginCode(BaseModel, table=True):
    """A short-lived email one-time code for the anti-bot login step. Stored
    hashed; one active code per user (old ones are replaced)."""

    __tablename__ = "email_login_codes"

    user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    code_hash: str = Field(max_length=128)
    expires_at: datetime
    attempts: int = Field(default=0)
    used_at: datetime | None = Field(default=None)


class RecoveryCode(BaseModel, table=True):
    """One-time 2FA recovery codes (stored hashed; shown to the user once)."""

    __tablename__ = "recovery_codes"

    user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    code_hash: str = Field(max_length=128, index=True)
    used_at: datetime | None = Field(default=None)


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

"""SocialConnection — OAuth-connected social accounts (Phase 2 M5).

One row per connected Facebook Page or Instagram Business Account.
Tokens are never stored here; they live in OpenBao (token_ref holds the KV path).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel
from app.models.social import SocialPlatform


class SocialConnectionStatus(StrEnum):
    active = "active"
    error = "error"
    expired = "expired"
    revoked = "revoked"


class SocialConnection(TenantModel, table=True):
    __tablename__ = "social_connections"

    platform: SocialPlatform = Field(
        sa_type=sa.String(20), index=True,
    )
    external_id: str = Field(max_length=200, index=True)
    handle: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=300)
    scopes: list = Field(default_factory=list, sa_type=JSON)
    status: SocialConnectionStatus = Field(
        default=SocialConnectionStatus.active,
        sa_type=sa.String(16),
        index=True,
    )
    token_ref: str = Field(max_length=500)
    connected_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    expires_at: datetime | None = Field(default=None)
    platform_meta: dict = Field(default_factory=dict, sa_type=JSON)

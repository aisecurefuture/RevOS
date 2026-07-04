"""Pydantic schemas for SocialConnection (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.social import SocialPlatform
from app.models.social_connection import SocialConnectionStatus


class SocialConnectionOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID | None
    platform: SocialPlatform
    external_id: str
    handle: str | None
    display_name: str | None
    scopes: list
    status: SocialConnectionStatus
    connected_by: uuid.UUID
    expires_at: datetime | None
    platform_meta: dict
    created_at: datetime


class FacebookPageOut(BaseModel):
    page_id: str
    name: str
    category: str | None
    has_instagram: bool
    ig_account_id: str | None


class ConnectUrlOut(BaseModel):
    url: str


class SubmitForApprovalOut(BaseModel):
    approval_request_id: uuid.UUID
    message: str

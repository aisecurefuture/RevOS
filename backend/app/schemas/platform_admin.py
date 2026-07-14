"""Schemas for the platform super-admin console (/admin)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminAccountOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    type: str
    owner_email: str | None = None
    member_count: int
    disabled: bool
    disabled_reason: str | None = None
    created_at: datetime


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    locked: bool
    failed_login_count: int
    email_verified: bool
    created_at: datetime


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lead_email: EmailStr
    lead_name: str | None = Field(default=None, max_length=200)


class CreateTenantOut(BaseModel):
    account_id: uuid.UUID
    name: str
    slug: str
    lead_email: str
    invited: bool


class DisableAccountRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)

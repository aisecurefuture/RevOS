"""AI draft-generation schemas. All responses are drafts for human review."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class DraftEmailRequest(BaseModel):
    brand_id: uuid.UUID
    goal: str = Field(min_length=1, max_length=300)
    audience: str | None = Field(default=None, max_length=200)


class DraftSocialRequest(BaseModel):
    brand_id: uuid.UUID
    platform: str = Field(default="linkedin", max_length=20)
    topic: str = Field(min_length=1, max_length=300)


class LandingCopyRequest(BaseModel):
    brand_id: uuid.UUID
    offer: str = Field(min_length=1, max_length=300)
    audience: str | None = Field(default=None, max_length=200)


class LeadMagnetRequest(BaseModel):
    brand_id: uuid.UUID
    audience: str | None = Field(default=None, max_length=200)
    count: int = Field(default=5, ge=1, le=10)


class BrandRef(BaseModel):
    brand_id: uuid.UUID


class DraftResult(BaseModel):
    text: str
    source: str  # "ai" | "template" — never auto-applied


class AIStatus(BaseModel):
    available: bool
    provider: str

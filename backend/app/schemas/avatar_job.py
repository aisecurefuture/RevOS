"""Schemas for avatar video generation jobs (Phase 3 M3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.social import SocialPlatform


class AvatarJobCreate(BaseModel):
    persona_identity_id: uuid.UUID
    script: str = Field(min_length=1, max_length=5000)
    target_seconds: int = Field(default=15)


class AvatarJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    persona_identity_id: uuid.UUID
    brand_id: uuid.UUID | None
    script: str
    target_seconds: int
    status: str
    estimated_seconds: int | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    # Derived — never expose the raw storage key.
    has_output: bool = False

    @classmethod
    def from_job(cls, job) -> "AvatarJobOut":
        out = cls.model_validate(job)
        out.has_output = bool(job.output_path)
        return out


class AvatarPublishRequest(BaseModel):
    platform: SocialPlatform
    caption: str | None = Field(default=None, max_length=3000)
    burn_captions: bool = True


class AvatarPublishOut(BaseModel):
    post_id: uuid.UUID
    approval_request_id: uuid.UUID
    platform: str

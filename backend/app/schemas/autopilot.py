"""Schemas for the content autopilot (Phase 3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AutopilotConfigUpdate(BaseModel):
    enabled: bool | None = None
    auto_publish: bool | None = None
    platforms: list[str] | None = None
    posts_per_run: int | None = Field(default=None, ge=1, le=5)
    run_interval_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    content_themes: list[str] | None = None
    default_cta: str | None = Field(default=None, max_length=300)


class AutopilotConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    brand_id: uuid.UUID
    enabled: bool
    auto_publish: bool
    platforms: list
    posts_per_run: int
    run_interval_hours: int
    content_themes: list
    default_cta: str | None
    last_run_at: datetime | None


class AutopilotRunOut(BaseModel):
    generated: int
    published: int
    queued: int
    blocked: int
    skipped: int

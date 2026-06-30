"""Media pipeline schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MediaVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    media_asset_id: uuid.UUID
    platform: str
    purpose: str
    aspect_ratio: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    size_bytes: int | None = None
    is_ai_enhanced: bool
    state: str


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    kind: str
    original_filename: str
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    size_bytes: int | None = None
    status: str
    created_at: datetime


class MediaAssetDetailOut(MediaAssetOut):
    variants: list[MediaVariantOut] = []


class ProcessRequest(BaseModel):
    # Which platforms to render for; empty = all applicable.
    platforms: list[str] = Field(default_factory=list)
    # Deterministic enhancement (autocontrast + sharpen). AI enhancement is
    # wired through the AI provider in Module 14.
    enhance: bool = False

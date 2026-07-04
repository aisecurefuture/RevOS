"""Media assets and their per-platform renditions.

A MediaAsset is the **immutable original** upload (write-once). Every transform
produces a new MediaVariant file — the original is never modified. Variants are
approval-gated before they can be attached to a social post.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel
from app.models.content import ContentState


class MediaKind(StrEnum):
    image = "image"
    video = "video"


class MediaStatus(StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class MediaAsset(TenantModel, table=True):
    __tablename__ = "media_assets"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    uploader_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    kind: MediaKind = Field(sa_type=sa.String, max_length=12, index=True)
    original_filename: str = Field(max_length=400)
    original_path: str = Field(max_length=600)        # storage key — never overwritten
    mime_type: str | None = Field(default=None, max_length=120)
    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)
    size_bytes: int | None = Field(default=None)
    checksum: str | None = Field(default=None, index=True, max_length=64)  # sha256
    status: MediaStatus = Field(
        default=MediaStatus.uploaded, sa_type=sa.String, max_length=16, index=True
    )
    meta: dict = Field(default_factory=dict, sa_type=JSON)


class MediaVariant(TenantModel, table=True):
    __tablename__ = "media_variants"

    media_asset_id: uuid.UUID = Field(foreign_key="media_assets.id", index=True)
    platform: str = Field(max_length=20, index=True)
    purpose: str = Field(max_length=40)               # feed_square | story | reel | thumbnail ...
    aspect_ratio: str | None = Field(default=None, max_length=12)
    path: str = Field(max_length=600)                 # storage key of the rendition
    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)
    format: str | None = Field(default=None, max_length=12)
    size_bytes: int | None = Field(default=None)
    is_ai_enhanced: bool = Field(default=False)
    enhancement: dict = Field(default_factory=dict, sa_type=JSON)
    # Reuses the content approval state machine — approved before social use.
    state: ContentState = Field(
        default=ContentState.draft, sa_type=sa.String, max_length=16, index=True
    )
    approval_request_id: uuid.UUID | None = Field(
        default=None, foreign_key="approval_requests.id"
    )
    meta: dict = Field(default_factory=dict, sa_type=JSON)

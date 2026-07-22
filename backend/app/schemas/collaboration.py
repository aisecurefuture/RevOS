"""Collaboration workspace schemas (CW1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.collaboration import (
    ApprovalDecision,
    AssetKind,
    AssetState,
    CollaborationKind,
    CollaborationState,
    DeliverableStatus,
)
from app.models.social import SocialPlatform


class CollaborationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_request_id: uuid.UUID
    brand_account_id: uuid.UUID
    creator_account_id: uuid.UUID
    creator_id: uuid.UUID
    product_id: uuid.UUID | None = None
    kind: CollaborationKind
    state: CollaborationState
    title: str | None = None
    ended_at: datetime | None = None
    created_at: datetime


class ShareBrandBookCreate(BaseModel):
    brand_id: uuid.UUID
    expires_at: datetime | None = None


class CollaborationShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_id: uuid.UUID
    shared_by_account_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    scope: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    status: str
    created_at: datetime


class SharedBrandBookOut(BaseModel):
    """The consumer view of a shared Brand Book — the fields useful to a
    collaborator (identity, messaging, and guardrails), not internal metadata."""

    model_config = ConfigDict(from_attributes=True)

    brand_id: uuid.UUID
    mission: str | None = None
    vision: str | None = None
    positioning: str | None = None
    elevator_pitch: str | None = None
    target_summary: str | None = None
    key_messages: list = Field(default_factory=list)
    core_values: list = Field(default_factory=list)
    brand_story: str | None = None
    voice_spectrum: dict = Field(default_factory=dict)
    banned_terms: list = Field(default_factory=list)
    required_disclaimers: list = Field(default_factory=list)
    is_published: bool = False


# --- CW2: shared assets + two-sided review-before-post ----------------------
class AssetCreate(BaseModel):
    kind: AssetKind
    title: str | None = Field(default=None, max_length=250)
    caption: str | None = Field(default=None, max_length=5000)
    media_urls: list[str] = Field(default_factory=list)


class AssetVersionCreate(BaseModel):
    caption: str | None = Field(default=None, max_length=5000)
    media_urls: list[str] = Field(default_factory=list)


class AssetCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    version: int | None = None


class AssetDecisionCreate(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AssetPublishCreate(BaseModel):
    brand_id: uuid.UUID
    platform: SocialPlatform


class CollaborationAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_id: uuid.UUID
    created_by_account_id: uuid.UUID
    kind: AssetKind
    title: str | None = None
    current_version: int
    state: AssetState
    linked_social_post_id: uuid.UUID | None = None
    created_at: datetime


class AssetVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    version: int
    created_by_account_id: uuid.UUID
    caption: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    created_at: datetime


class AssetCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    version: int | None = None
    author_account_id: uuid.UUID
    author_user_id: uuid.UUID
    body: str
    created_at: datetime


class AssetApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    version: int
    account_id: uuid.UUID
    user_id: uuid.UUID
    decision: ApprovalDecision
    note: str | None = None
    created_at: datetime


# --- CW3: briefs, deliverables, disclosure & usage rights -------------------
class BriefUpsert(BaseModel):
    """Full replace — the brief is a shared doc, not a patch-field API."""

    goals: str | None = Field(default=None, max_length=5000)
    key_messages: list[str] = Field(default_factory=list)
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    deadline: datetime | None = None
    requires_disclosure: bool = True
    disclosure_text: str | None = Field(default=None, max_length=200)
    usage_rights: str | None = Field(default=None, max_length=5000)
    usage_duration_days: int | None = Field(default=None, ge=0)
    whitelisting_allowed: bool = False
    boost_allowed: bool = False


class CollaborationBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_id: uuid.UUID
    updated_by_account_id: uuid.UUID
    goals: str | None = None
    key_messages: list[str] = Field(default_factory=list)
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    deadline: datetime | None = None
    requires_disclosure: bool
    disclosure_text: str | None = None
    usage_rights: str | None = None
    usage_duration_days: int | None = None
    whitelisting_allowed: bool
    boost_allowed: bool
    created_at: datetime
    updated_at: datetime


class DeliverableCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None


class DeliverableUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    status: DeliverableStatus | None = None
    asset_id: uuid.UUID | None = None


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_id: uuid.UUID
    created_by_account_id: uuid.UUID
    title: str
    description: str | None = None
    due_at: datetime | None = None
    status: DeliverableStatus
    asset_id: uuid.UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime


class OfferImportCreate(BaseModel):
    """Seed a marketplace product from an existing offer + marketplace fields."""

    offer_id: uuid.UUID
    industry: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=120)
    status: str | None = None
    discoverable: bool = False


# --- Phase 6: full messaging threads ----------------------------------------
class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageReport(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CollaborationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_id: uuid.UUID
    sender_account_id: uuid.UUID
    sender_user_id: uuid.UUID
    body: str
    is_flagged: bool
    flagged_reason: str | None = None
    flagged_at: datetime | None = None
    created_at: datetime

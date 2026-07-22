"""Matching engine schemas: creators, products, target audience."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.matching import (
    AudienceSource,
    CollaborationDirection,
    CollaborationStatus,
    CreatorManagement,
    CreatorStatus,
    MatchProductStatus,
)


class IndustryAffinity(BaseModel):
    """One weighted vertical a creator/product belongs to (industries.ts slug)."""

    industry: str = Field(min_length=1, max_length=80)
    weight: float = Field(default=1.0, ge=0, le=1)


class TargetAudience(BaseModel):
    """A product's ideal-audience spec — what the demographics score measures
    a creator's audience against. All optional; absent fields don't penalize."""

    age_min: int | None = Field(default=None, ge=0, le=120)
    age_max: int | None = Field(default=None, ge=0, le=120)
    gender_skew: str | None = Field(default=None, max_length=20)   # "female" | "male" | "balanced"
    locations: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)


# --- Creator ----------------------------------------------------------------
class CreatorCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    handle: str | None = Field(default=None, max_length=200)
    primary_platform: str | None = Field(default=None, max_length=20)
    bio: str | None = None
    industry: str | None = Field(default=None, max_length=80)
    industries: list[IndustryAffinity] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=120)
    topics: list[str] = Field(default_factory=list)
    discoverable: bool = False
    location: str | None = Field(default=None, max_length=160)
    management: CreatorManagement = CreatorManagement.self_managed
    follower_count: int | None = Field(default=None, ge=0)
    engagement_rate: float | None = Field(default=None, ge=0)
    avg_views: int | None = Field(default=None, ge=0)
    demographics: dict = Field(default_factory=dict)
    audience_source: AudienceSource = AudienceSource.manual
    notes: str | None = Field(default=None, max_length=5000)
    contact_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None       # link a Brand → reuse its Brand Book


class CreatorUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    handle: str | None = Field(default=None, max_length=200)
    primary_platform: str | None = Field(default=None, max_length=20)
    bio: str | None = None
    industry: str | None = Field(default=None, max_length=80)
    industries: list[IndustryAffinity] | None = None
    category: str | None = Field(default=None, max_length=120)
    topics: list[str] | None = None
    location: str | None = Field(default=None, max_length=160)
    management: CreatorManagement | None = None
    status: CreatorStatus | None = None
    discoverable: bool | None = None
    follower_count: int | None = Field(default=None, ge=0)
    engagement_rate: float | None = Field(default=None, ge=0)
    avg_views: int | None = Field(default=None, ge=0)
    demographics: dict | None = None
    audience_source: AudienceSource | None = None
    notes: str | None = Field(default=None, max_length=5000)
    contact_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None       # link a Brand → reuse its Brand Book


class CreatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    handle: str | None = None
    primary_platform: str | None = None
    bio: str | None = None
    industry: str | None = None
    industries: list[IndustryAffinity] = Field(default_factory=list)
    size_tier: str | None = None
    category: str | None = None
    topics: list[str] = Field(default_factory=list)
    location: str | None = None
    management: str
    status: str
    discoverable: bool = False
    follower_count: int | None = None
    engagement_rate: float | None = None
    avg_views: int | None = None
    demographics: dict = Field(default_factory=dict)
    audience_source: str
    audience_captured_at: datetime | None = None
    notes: str | None = None
    contact_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None       # link a Brand → reuse its Brand Book
    claimed_by_user_id: uuid.UUID | None = None
    claimed_at: datetime | None = None
    created_at: datetime


class CreatorClaimInviteOut(BaseModel):
    token: str
    claim_url: str
    expires_in_days: int


class CreatorClaimRequest(BaseModel):
    token: str


# --- MatchProduct -----------------------------------------------------------
class MatchProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    brand_id: uuid.UUID | None = None
    description: str | None = None
    category: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=80)
    industries: list[IndustryAffinity] = Field(default_factory=list)
    status: MatchProductStatus = MatchProductStatus.draft
    discoverable: bool = False
    target_audience: TargetAudience = Field(default_factory=TargetAudience)
    budget_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", max_length=3)
    offer_id: uuid.UUID | None = None


class MatchProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    brand_id: uuid.UUID | None = None
    description: str | None = None
    category: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=80)
    industries: list[IndustryAffinity] | None = None
    status: MatchProductStatus | None = None
    discoverable: bool | None = None
    target_audience: TargetAudience | None = None
    budget_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    offer_id: uuid.UUID | None = None


class MatchProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand_id: uuid.UUID | None = None
    description: str | None = None
    category: str | None = None
    industry: str | None = None
    industries: list[IndustryAffinity] = Field(default_factory=list)
    status: str
    discoverable: bool = False
    target_audience: dict = Field(default_factory=dict)
    budget_cents: int | None = None
    currency: str
    offer_id: uuid.UUID | None = None
    created_at: datetime


# --- Match results ----------------------------------------------------------
class DimensionOut(BaseModel):
    key: str
    score: float
    weight: float
    available: bool
    detail: str


class MatchScoreOut(BaseModel):
    overall: float
    coverage: float
    rationale: str
    dimensions: list[DimensionOut]


class CreatorMatchOut(BaseModel):
    creator: CreatorOut
    score: MatchScoreOut


class ProductMatchOut(BaseModel):
    product: MatchProductOut
    score: MatchScoreOut


# --- Discovery (cross-tenant, consent-gated; score present only when ranked) --
class CreatorDiscoveryOut(BaseModel):
    creator: CreatorOut
    score: MatchScoreOut | None = None


class ProductDiscoveryOut(BaseModel):
    product: MatchProductOut
    score: MatchScoreOut | None = None


# --- Collaboration requests -------------------------------------------------
class CollaborationRequestCreate(BaseModel):
    direction: CollaborationDirection
    creator_id: uuid.UUID
    product_id: uuid.UUID | None = None      # required for brand→creator; context for creator→brand
    message: str = Field(min_length=1, max_length=2000)


class BrokerCollaborationCreate(CollaborationRequestCreate):
    """A platform admin brokering a request between two parties."""

    initiator_account_id: uuid.UUID


class CollaborationRespond(BaseModel):
    accept: bool
    note: str | None = Field(default=None, max_length=2000)


class CollaborationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    direction: str
    status: str
    initiator_account_id: uuid.UUID
    initiator_user_id: uuid.UUID
    creator_id: uuid.UUID
    product_id: uuid.UUID | None = None
    recipient_account_id: uuid.UUID | None = None
    message: str
    response_note: str | None = None
    response_channel: str | None = None
    brokered_by_user_id: uuid.UUID | None = None
    responded_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


# --- Public creator page + QR sharing ---------------------------------------
# Server-enforced allow-list — a creator can only surface fields on this list,
# never anything else, regardless of what the client sends.
PUBLIC_CREATOR_FIELDS: frozenset[str] = frozenset({
    "reputation", "industry", "bio", "location", "certifications",
    "follower_count", "engagement_rate", "topics", "size_tier",
})


class PublicPageSettingsUpdate(BaseModel):
    enabled: bool
    slug: str | None = Field(default=None, max_length=140)
    fields: list[str] = Field(default_factory=list)


class PublicPageSettingsOut(BaseModel):
    enabled: bool
    slug: str | None = None
    fields: list[str]
    share_url: str | None = None
    view_count: int


class PublicReputationOut(BaseModel):
    overall: float
    tier: str
    percentile: int | None = None


class PublicCertificationOut(BaseModel):
    name: str
    issuer: str | None = None
    verified: bool


class PublicCreatorPageOut(BaseModel):
    display_name: str
    handle: str | None = None
    slug: str
    bio: str | None = None
    industry: str | None = None
    location: str | None = None
    size_tier: str | None = None
    follower_count: int | None = None
    engagement_rate: float | None = None
    engagement_benchmark: dict | None = None   # BenchmarkOut shape — cohort or industry-report
    topics: list[str] = Field(default_factory=list)
    reputation: PublicReputationOut | None = None
    certifications: list[PublicCertificationOut] = Field(default_factory=list)
    view_count: int

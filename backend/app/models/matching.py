"""Creator↔Product matching (Phase 3 — AI Matching Engine).

A **Creator** is a person promoted/matched to products, owned by the tenant.
One creator has many connected accounts (``SocialConnection.creator_id``, one
row per platform) — the account's audience *is* the creator's audience, so that
stays one-to-many. Team/agency co-management is a separate, many-to-many
relationship (``CreatorManager``): several users can manage one creator and one
user manages many.

A **MatchProduct** is a sponsorable product/campaign the engine ranks creators
against, on audience fit, engagement, demographics, and brand compatibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class CreatorManagement(StrEnum):
    self_managed = "self_managed"      # the creator runs their own accounts
    agency_managed = "agency_managed"  # this tenant/agency manages them


class AudienceSource(StrEnum):
    manual = "manual"                  # entered/imported by hand
    connected = "connected"            # pulled from a connected account's insights
    third_party = "third_party"        # benchmarked via an external data provider


class CreatorStatus(StrEnum):
    active = "active"
    archived = "archived"


class Creator(TenantModel, table=True):
    __tablename__ = "creators"

    display_name: str = Field(index=True, max_length=200)
    handle: str | None = Field(default=None, max_length=200)          # canonical/primary handle
    primary_platform: str | None = Field(default=None, max_length=20)  # SocialPlatform value
    bio: str | None = Field(default=None, sa_type=sa.Text)

    # Normalized primary vertical (industries.ts slug) — the cohort key that
    # rolls up to the 11 categories for within/cross-industry ratings.
    industry: str | None = Field(default=None, index=True, max_length=80)
    # Weighted multi-vertical affinity: [{"industry": slug, "weight": 0..1}].
    industries: list = Field(default_factory=list, sa_type=JSON)
    # Follower size tier (nano/micro/mid/macro/mega) — second rating-cohort axis,
    # derived from follower_count on write.
    size_tier: str | None = Field(default=None, index=True, max_length=16)

    category: str | None = Field(default=None, index=True, max_length=120)  # free sub-niche
    topics: list = Field(default_factory=list, sa_type=JSON)           # content topics / tags
    location: str | None = Field(default=None, max_length=160)         # creator's own base location

    management: CreatorManagement = Field(
        default=CreatorManagement.self_managed, sa_type=sa.String, max_length=20, index=True,
    )
    status: CreatorStatus = Field(
        default=CreatorStatus.active, sa_type=sa.String, max_length=16, index=True,
    )

    # --- Current audience snapshot (time-series + benchmarks come in Phase 3) ---
    follower_count: int | None = Field(default=None)
    engagement_rate: float | None = Field(default=None)   # 0..1 (likes+comments per follower)
    avg_views: int | None = Field(default=None)
    # {"age": {"18-24": 0.3, ...}, "gender": {"female": 0.6, ...},
    #  "locations": [{"name": "Austin, TX", "share": 0.2}], "interests": ["real estate"]}
    demographics: dict = Field(default_factory=dict, sa_type=JSON)
    audience_source: AudienceSource = Field(
        default=AudienceSource.manual, sa_type=sa.String, max_length=16,
    )
    audience_captured_at: datetime | None = Field(default=None)

    notes: str | None = Field(default=None, max_length=5000)
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id", index=True)


class CreatorManager(TenantModel, table=True):
    """Many-to-many: users who co-manage a creator (agency/team case)."""

    __tablename__ = "creator_managers"

    creator_id: uuid.UUID = Field(foreign_key="creators.id", index=True)
    admin_user_id: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    role: str | None = Field(default=None, max_length=60)   # e.g. "manager", "assistant"

    __table_args__ = (
        sa.UniqueConstraint("creator_id", "admin_user_id", name="uq_creator_manager"),
    )


class MatchProductStatus(StrEnum):
    draft = "draft"
    active = "active"
    archived = "archived"


class MatchProduct(TenantModel, table=True):
    """A sponsorable product/campaign creators are ranked against."""

    __tablename__ = "match_products"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    name: str = Field(index=True, max_length=250)
    description: str | None = Field(default=None, sa_type=sa.Text)
    category: str | None = Field(default=None, index=True, max_length=120)
    # Target vertical(s) — same taxonomy as Creator, for industry-aware matching.
    industry: str | None = Field(default=None, index=True, max_length=80)
    industries: list = Field(default_factory=list, sa_type=JSON)
    status: MatchProductStatus = Field(
        default=MatchProductStatus.draft, sa_type=sa.String, max_length=16, index=True,
    )

    # Ideal-audience spec the demographics score is measured against.
    # {"age_min": 25, "age_max": 44, "gender_skew": "female",
    #  "locations": ["US", "Austin, TX"], "interests": ["home buying", "interiors"]}
    target_audience: dict = Field(default_factory=dict, sa_type=JSON)

    budget_cents: int | None = Field(default=None)
    currency: str = Field(default="USD", max_length=3)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id", index=True)  # optional link

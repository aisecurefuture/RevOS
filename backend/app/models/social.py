"""Social media: connected accounts, social campaigns, scheduled posts.

No scraping. Adapters publish only via official APIs when keys are present;
otherwise posts stay as approved drafts for copy-paste. Access tokens are NOT
stored here in plaintext — `connection_meta` holds only non-secret references.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel
from app.models.content import ContentState


class SocialPlatform(StrEnum):
    linkedin = "linkedin"
    instagram = "instagram"
    facebook = "facebook"
    twitter = "twitter"
    youtube = "youtube"
    tiktok = "tiktok"


class SocialCampaignStatus(StrEnum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class SocialAccount(TenantModel, table=True):
    __tablename__ = "social_accounts"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    platform: SocialPlatform = Field(sa_type=sa.String, max_length=20)
    handle: str | None = Field(default=None, max_length=200)
    external_id: str | None = Field(default=None, max_length=200)
    is_connected: bool = Field(default=False)
    # Non-secret connection state only (token IDs/expiry, never raw tokens).
    connection_meta: dict = Field(default_factory=dict, sa_type=JSON)


class SocialCampaign(TenantModel, table=True):
    """A multi-platform social campaign (e.g. the Hao influencer campaign)."""

    __tablename__ = "social_campaigns"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    campaign_id: uuid.UUID | None = Field(default=None, foreign_key="campaigns.id")
    persona_id: uuid.UUID | None = Field(default=None, foreign_key="buyer_personas.id")
    name: str = Field(max_length=200)
    objective: str | None = Field(default=None, max_length=400)
    theme: str | None = Field(default=None, max_length=200)
    platforms: list = Field(default_factory=list, sa_type=JSON)
    status: SocialCampaignStatus = Field(
        default=SocialCampaignStatus.draft, sa_type=sa.String, max_length=16, index=True
    )
    start_at: datetime | None = Field(default=None)
    end_at: datetime | None = Field(default=None)
    settings: dict = Field(default_factory=dict, sa_type=JSON)


class SocialPost(TenantModel, table=True):
    __tablename__ = "social_posts"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    social_campaign_id: uuid.UUID | None = Field(
        default=None, foreign_key="social_campaigns.id", index=True
    )
    social_account_id: uuid.UUID | None = Field(default=None, foreign_key="social_accounts.id")
    content_item_id: uuid.UUID | None = Field(default=None, foreign_key="content_items.id")
    approval_request_id: uuid.UUID | None = Field(
        default=None, foreign_key="approval_requests.id"
    )

    platform: SocialPlatform = Field(sa_type=sa.String, max_length=20, index=True)
    caption: str | None = Field(default=None, sa_type=sa.Text)
    media_urls: list = Field(default_factory=list, sa_type=JSON)
    hashtags: list = Field(default_factory=list, sa_type=JSON)
    # Reuses the content approval state machine.
    state: ContentState = Field(
        default=ContentState.draft, sa_type=sa.String, max_length=16, index=True
    )
    scheduled_at: datetime | None = Field(default=None, index=True)
    published_at: datetime | None = Field(default=None)
    external_post_id: str | None = Field(default=None, max_length=200)
    # Engagement placeholders, populated from platform APIs when connected.
    metrics: dict = Field(default_factory=dict, sa_type=JSON)

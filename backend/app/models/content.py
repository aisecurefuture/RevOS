"""Content engine: items, calendars, pillars, hooks, CTAs, hashtags.

Content moves through an explicit approval state machine and is never published
automatically without an approved state (and, for social, an approval request).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class ContentState(StrEnum):
    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
    scheduled = "scheduled"
    published = "published"
    archived = "archived"


class ContentChannel(StrEnum):
    linkedin = "linkedin"
    twitter = "twitter"
    instagram = "instagram"
    facebook = "facebook"
    youtube_short = "youtube_short"
    tiktok = "tiktok"
    blog = "blog"
    newsletter = "newsletter"
    video_15 = "video_15"
    video_30 = "video_30"
    video_45 = "video_45"
    video_60 = "video_60"
    video_script = "video_script"


class ContentCalendar(TenantModel, table=True):
    """A planning container grouping content items over a date range."""

    __tablename__ = "content_calendars"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, sa_type=sa.Text)
    theme: str | None = Field(default=None, max_length=200)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)


class Pillar(TenantModel, table=True):
    """Reusable content pillar / theme for a brand."""

    __tablename__ = "pillars"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    name: str = Field(max_length=160)
    description: str | None = Field(default=None, sa_type=sa.Text)
    color: str | None = Field(default=None, max_length=16)


class Hook(TenantModel, table=True):
    """Reusable opening hook line (global if brand_id is NULL)."""

    __tablename__ = "hooks"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    text: str = Field(sa_type=sa.Text)
    category: str | None = Field(default=None, max_length=80)
    channel: str | None = Field(default=None, max_length=40)
    performance_score: float | None = Field(default=None)


class CTA(TenantModel, table=True):
    """Reusable call-to-action (global if brand_id is NULL)."""

    __tablename__ = "ctas"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    label: str = Field(max_length=160)
    url: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=400)
    category: str | None = Field(default=None, max_length=80)


class Hashtag(TenantModel, table=True):
    __tablename__ = "hashtags"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    tag: str = Field(index=True, max_length=120)
    group_name: str | None = Field(default=None, max_length=120)
    channel: str | None = Field(default=None, max_length=40)


class ContentItem(TenantModel, table=True):
    __tablename__ = "content_items"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    campaign_id: uuid.UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    calendar_id: uuid.UUID | None = Field(default=None, foreign_key="content_calendars.id")
    social_campaign_id: uuid.UUID | None = Field(
        default=None, foreign_key="social_campaigns.id", index=True
    )
    pillar_id: uuid.UUID | None = Field(default=None, foreign_key="pillars.id")
    hook_id: uuid.UUID | None = Field(default=None, foreign_key="hooks.id")
    cta_id: uuid.UUID | None = Field(default=None, foreign_key="ctas.id")
    author_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    approved_by_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    approval_request_id: uuid.UUID | None = Field(
        default=None, foreign_key="approval_requests.id"
    )
    # Self-reference for repurposing one piece into many (blog -> social).
    source_content_id: uuid.UUID | None = Field(default=None, foreign_key="content_items.id")

    title: str = Field(max_length=300)
    channel: ContentChannel = Field(
        default=ContentChannel.linkedin, sa_type=sa.String, max_length=20, index=True
    )
    body: str | None = Field(default=None, sa_type=sa.Text)
    media_urls: list = Field(default_factory=list, sa_type=JSON)
    hashtags: list = Field(default_factory=list, sa_type=JSON)
    # For video drafts: scenes/script/timing + total duration.
    video_script: dict = Field(default_factory=dict, sa_type=JSON)
    duration_seconds: int | None = Field(default=None)

    state: ContentState = Field(
        default=ContentState.draft, sa_type=sa.String, max_length=16, index=True
    )
    ai_generated: bool = Field(default=False)
    scheduled_at: datetime | None = Field(default=None, index=True)
    published_at: datetime | None = Field(default=None)
    notes: str | None = Field(default=None, sa_type=sa.Text)

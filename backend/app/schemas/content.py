"""Content engine schemas: items, libraries, calendar, social."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.content import ContentChannel
from app.models.social import SocialPlatform


# --- Content items ----------------------------------------------------------
class ContentItemCreate(BaseModel):
    brand_id: uuid.UUID
    channel: ContentChannel = ContentChannel.linkedin
    title: str = Field(min_length=1, max_length=300)
    body: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    pillar_id: uuid.UUID | None = None
    hook_id: uuid.UUID | None = None
    cta_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    calendar_id: uuid.UUID | None = None
    social_campaign_id: uuid.UUID | None = None
    video_script: dict = Field(default_factory=dict)
    duration_seconds: int | None = None
    scheduled_at: datetime | None = None
    notes: str | None = None


class ContentItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    channel: ContentChannel | None = None
    body: str | None = None
    media_urls: list[str] | None = None
    hashtags: list[str] | None = None
    pillar_id: uuid.UUID | None = None
    hook_id: uuid.UUID | None = None
    cta_id: uuid.UUID | None = None
    video_script: dict | None = None
    duration_seconds: int | None = None
    notes: str | None = None


class ContentItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    channel: str
    title: str
    body: str | None = None
    media_urls: list = []
    hashtags: list = []
    state: str
    ai_generated: bool
    duration_seconds: int | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime


class ScheduleRequest(BaseModel):
    scheduled_at: datetime


# --- Libraries --------------------------------------------------------------
class PillarCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    color: str | None = Field(default=None, max_length=16)


class HookCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    text: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=80)
    channel: str | None = Field(default=None, max_length=40)


class CTACreate(BaseModel):
    brand_id: uuid.UUID | None = None
    label: str = Field(min_length=1, max_length=160)
    url: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=400)
    category: str | None = Field(default=None, max_length=80)
    offer_id: uuid.UUID | None = None


class HashtagCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    tag: str = Field(min_length=1, max_length=120)
    group_name: str | None = Field(default=None, max_length=120)
    channel: str | None = Field(default=None, max_length=40)


class LibraryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None


class PillarOut(LibraryItemOut):
    name: str
    description: str | None = None
    color: str | None = None


class HookOut(LibraryItemOut):
    text: str
    category: str | None = None
    channel: str | None = None


class CTAOut(LibraryItemOut):
    label: str
    url: str | None = None
    category: str | None = None


class HashtagOut(LibraryItemOut):
    tag: str
    group_name: str | None = None


# --- Calendar ---------------------------------------------------------------
class CalendarCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    theme: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None


class CalendarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    theme: str | None = None
    start_date: date | None = None
    end_date: date | None = None


# --- Idea generation (template-based; AI provider wired in Module 14) --------
class IdeaRequest(BaseModel):
    brand_id: uuid.UUID
    channel: ContentChannel = ContentChannel.linkedin
    count: int = Field(default=5, ge=1, le=20)
    topic: str | None = Field(default=None, max_length=200)


class IdeaResult(BaseModel):
    ideas: list[str]
    source: str  # "ai" | "template"


# --- Social -----------------------------------------------------------------
class SocialAccountCreate(BaseModel):
    brand_id: uuid.UUID
    platform: SocialPlatform
    handle: str | None = Field(default=None, max_length=200)


class SocialAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    platform: str
    handle: str | None = None
    is_connected: bool


class SocialCampaignCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    objective: str | None = Field(default=None, max_length=400)
    theme: str | None = Field(default=None, max_length=200)
    platforms: list[str] = Field(default_factory=list)


class SocialCampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    objective: str | None = None
    theme: str | None = None
    platforms: list = []
    status: str
    created_at: datetime


class SocialPostCreate(BaseModel):
    brand_id: uuid.UUID
    platform: SocialPlatform
    social_campaign_id: uuid.UUID | None = None
    caption: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    scheduled_at: datetime | None = None


class SocialPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    platform: str
    social_campaign_id: uuid.UUID | None = None
    caption: str | None = None
    media_urls: list = []
    hashtags: list = []
    state: str
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    external_post_id: str | None = None


class PublishResult(BaseModel):
    published: bool
    mode: str  # "live" | "draft"
    message: str
    external_id: str | None = None

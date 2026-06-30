"""Landing page schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import HttpUrlStr


class LandingCreate(BaseModel):
    brand_id: uuid.UUID
    title: str = Field(min_length=1, max_length=250)
    slug: str | None = Field(default=None, max_length=160)
    template: str = Field(default="default", max_length=80)
    headline: str | None = Field(default=None, max_length=300)
    subheadline: str | None = Field(default=None, max_length=500)
    body_html: str | None = None  # sanitized server-side
    hero_image_url: HttpUrlStr | None = Field(default=None, max_length=500)
    cta_label: str | None = Field(default=None, max_length=120)
    cta_url: HttpUrlStr | None = Field(default=None, max_length=500)
    form_id: uuid.UUID | None = None
    offer_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    blocks: list = Field(default_factory=list)
    seo_meta: dict = Field(default_factory=dict)
    is_published: bool = False


class LandingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    template: str | None = Field(default=None, max_length=80)
    headline: str | None = Field(default=None, max_length=300)
    subheadline: str | None = Field(default=None, max_length=500)
    body_html: str | None = None
    hero_image_url: HttpUrlStr | None = Field(default=None, max_length=500)
    cta_label: str | None = Field(default=None, max_length=120)
    cta_url: HttpUrlStr | None = Field(default=None, max_length=500)
    form_id: uuid.UUID | None = None
    offer_id: uuid.UUID | None = None
    blocks: list | None = None
    seo_meta: dict | None = None
    is_published: bool | None = None


class LandingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    slug: str
    template: str
    headline: str | None = None
    subheadline: str | None = None
    body_html: str | None = None
    hero_image_url: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    form_id: uuid.UUID | None = None
    is_published: bool
    created_at: datetime

"""Campaigns, landing pages, forms, form submissions."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class CampaignStatus(StrEnum):
    draft = "draft"
    scheduled = "scheduled"
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class CampaignChannel(StrEnum):
    email = "email"
    social = "social"
    landing = "landing"
    multi = "multi"
    ads = "ads"


class FormType(StrEnum):
    newsletter = "newsletter"
    contact = "contact"
    consultation = "consultation"
    preorder = "preorder"
    download_gate = "download_gate"
    lead_magnet = "lead_magnet"
    waitlist = "waitlist"


class Campaign(TenantModel, table=True):
    __tablename__ = "campaigns"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    name: str = Field(index=True, max_length=250)
    slug: str = Field(index=True, max_length=160)
    objective: str | None = Field(default=None, max_length=300)
    status: CampaignStatus = Field(
        default=CampaignStatus.draft, sa_type=sa.String, max_length=16, index=True
    )
    channel: CampaignChannel = Field(default=CampaignChannel.email, sa_type=sa.String, max_length=12)
    theme: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    budget_cents: int | None = Field(default=None)
    start_at: datetime | None = Field(default=None)
    end_at: datetime | None = Field(default=None)
    settings: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (sa.UniqueConstraint("brand_id", "slug", name="uq_campaign_brand_slug"),)


class LandingPage(TenantModel, table=True):
    __tablename__ = "landing_pages"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    campaign_id: uuid.UUID | None = Field(default=None, foreign_key="campaigns.id", index=True)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    form_id: uuid.UUID | None = Field(default=None, foreign_key="forms.id")

    title: str = Field(max_length=250)
    slug: str = Field(unique=True, index=True, max_length=160)   # public URL slug
    template: str = Field(default="default", max_length=80)
    headline: str | None = Field(default=None, max_length=300)
    subheadline: str | None = Field(default=None, max_length=500)
    body_html: str | None = Field(default=None, sa_type=sa.Text)  # sanitized before render
    hero_image_url: str | None = Field(default=None, max_length=500)
    cta_label: str | None = Field(default=None, max_length=120)
    cta_url: str | None = Field(default=None, max_length=500)
    # Modular content blocks + SEO meta for flexible page composition.
    blocks: list = Field(default_factory=list, sa_type=JSON)
    seo_meta: dict = Field(default_factory=dict, sa_type=JSON)
    is_published: bool = Field(default=False, index=True)
    published_at: datetime | None = Field(default=None)


class Form(TenantModel, table=True):
    __tablename__ = "forms"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    campaign_id: uuid.UUID | None = Field(default=None, foreign_key="campaigns.id")
    lead_magnet_offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    segment_id: uuid.UUID | None = Field(default=None, foreign_key="segments.id")

    name: str = Field(max_length=200)
    slug: str = Field(unique=True, index=True, max_length=160)
    form_type: FormType = Field(default=FormType.newsletter, sa_type=sa.String, max_length=20)
    # Declarative field schema: [{name,label,type,required}, ...]
    fields: list = Field(default_factory=list, sa_type=JSON)
    consent_required: bool = Field(default=True)
    consent_text: str | None = Field(default=None, sa_type=sa.Text)
    double_optin: bool = Field(default=True)
    success_message: str | None = Field(default=None, max_length=500)
    redirect_url: str | None = Field(default=None, max_length=500)
    tags_to_apply: list = Field(default_factory=list, sa_type=JSON)
    notify_emails: list = Field(default_factory=list, sa_type=JSON)
    enroll_sequence_id: uuid.UUID | None = Field(default=None, foreign_key="sequences.id")
    embed_enabled: bool = Field(default=True)
    is_active: bool = Field(default=True)


class FormSubmission(TenantModel, table=True):
    __tablename__ = "form_submissions"

    form_id: uuid.UUID = Field(foreign_key="forms.id", index=True)
    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    lead_id: uuid.UUID | None = Field(default=None, foreign_key="leads.id", index=True)
    data: dict = Field(default_factory=dict, sa_type=JSON)
    utm: dict = Field(default_factory=dict, sa_type=JSON)
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=400)
    consent_given: bool = Field(default=False)
    is_spam: bool = Field(default=False)
    processed: bool = Field(default=False)

"""Brands and their messaging context: voice, audiences, buyer personas.

A Brand is the multi-tenant root. Nearly every other entity carries a
`brand_id`, so adding a new business/book/offer is pure data — no code change.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class BrandType(StrEnum):
    company = "company"
    personal = "personal"
    book = "book"
    influencer = "influencer"
    product = "product"


class Brand(TenantModel, table=True):
    __tablename__ = "brands"

    name: str = Field(index=True, max_length=200)
    slug: str = Field(unique=True, index=True, max_length=120)
    brand_type: BrandType = Field(default=BrandType.company, sa_type=sa.String, max_length=20)
    website_url: str | None = Field(default=None, max_length=500)
    tagline: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, sa_type=sa.Text)
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=16)
    is_active: bool = Field(default=True)
    # Per-brand funnel/CTA/automation config. `automation_enabled=False` here is
    # the brand-level kill switch for all outbound automation.
    settings: dict = Field(default_factory=dict, sa_type=JSON)
    # Full design system for brand-themed generated media (Pitch Video Studio
    # scenes, etc). Deliberately a flexible blob, not fixed columns — token
    # needs vary a lot per use case. Expected shape (all optional, renderers
    # must handle missing keys with sane fallbacks):
    #   {"colors": {"bg_dark": "#...", "bg_light": "#...", "surface": "#...",
    #               "card": "#...", "text": "#...", "muted": "#...",
    #               "muted_on_dark": "#...", "hairline": "#...",
    #               "hairline_on_dark": "#...", "accent": "#...",
    #               "chart_ramp": ["#...", ...]},
    #    "fonts": {"heading": "...", "body": "..."},
    #    "wordmark": "...", "pillars": ["...", ...]}
    design_tokens: dict = Field(default_factory=dict, sa_type=JSON)


class BrandVoice(TenantModel, table=True):
    """1:1 voice/style guide for a brand — drives AI drafts and templates."""

    __tablename__ = "brand_voices"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True, unique=True)
    tone: str | None = Field(default=None, max_length=300)          # e.g. "authoritative, plain"
    style_notes: str | None = Field(default=None, sa_type=sa.Text)
    writing_sample: str | None = Field(default=None, sa_type=sa.Text)
    do_list: list = Field(default_factory=list, sa_type=JSON)
    dont_list: list = Field(default_factory=list, sa_type=JSON)
    value_props: list = Field(default_factory=list, sa_type=JSON)
    vocabulary: list = Field(default_factory=list, sa_type=JSON)     # preferred terms


class Audience(TenantModel, table=True):
    """A targetable audience segment definition for a brand."""

    __tablename__ = "audiences"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    name: str = Field(max_length=200)
    description: str | None = Field(default=None, sa_type=sa.Text)
    # Declarative rule set (e.g. tags, source, score thresholds) for matching.
    segment_rules: dict = Field(default_factory=dict, sa_type=JSON)
    size_estimate: int | None = Field(default=None)


class BuyerPersona(TenantModel, table=True):
    __tablename__ = "buyer_personas"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    name: str = Field(max_length=200)                                # e.g. "CISO Carla"
    role_title: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, sa_type=sa.Text)
    goals: list = Field(default_factory=list, sa_type=JSON)
    pain_points: list = Field(default_factory=list, sa_type=JSON)
    objections: list = Field(default_factory=list, sa_type=JSON)
    channels: list = Field(default_factory=list, sa_type=JSON)
    demographics: dict = Field(default_factory=dict, sa_type=JSON)

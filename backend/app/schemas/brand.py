"""Brand, audience, persona, and brand-voice schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.brand import BrandType
from app.schemas.common import HttpUrlStr


# --- Brand ------------------------------------------------------------------
class BrandCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand_type: BrandType = BrandType.company
    slug: str | None = Field(default=None, max_length=120)
    website_url: HttpUrlStr | None = Field(default=None, max_length=500)
    tagline: str | None = Field(default=None, max_length=300)
    description: str | None = None
    logo_url: HttpUrlStr | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=16)
    settings: dict = Field(default_factory=dict)


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand_type: BrandType | None = None
    website_url: HttpUrlStr | None = Field(default=None, max_length=500)
    tagline: str | None = Field(default=None, max_length=300)
    description: str | None = None
    logo_url: HttpUrlStr | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=16)
    is_active: bool | None = None
    settings: dict | None = None


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    brand_type: str
    website_url: str | None = None
    tagline: str | None = None
    description: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    is_active: bool
    settings: dict = {}
    created_at: datetime


# --- Audience ---------------------------------------------------------------
class AudienceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    segment_rules: dict = Field(default_factory=dict)
    size_estimate: int | None = None


class AudienceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    segment_rules: dict | None = None
    size_estimate: int | None = None


class AudienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    description: str | None = None
    segment_rules: dict = {}
    size_estimate: int | None = None


# --- Buyer persona ----------------------------------------------------------
class PersonaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role_title: str | None = Field(default=None, max_length=200)
    summary: str | None = None
    goals: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    demographics: dict = Field(default_factory=dict)


class PersonaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role_title: str | None = Field(default=None, max_length=200)
    summary: str | None = None
    goals: list[str] | None = None
    pain_points: list[str] | None = None
    objections: list[str] | None = None
    channels: list[str] | None = None
    demographics: dict | None = None


class PersonaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    role_title: str | None = None
    summary: str | None = None
    goals: list[str] = []
    pain_points: list[str] = []
    objections: list[str] = []
    channels: list[str] = []
    demographics: dict = {}


# --- Brand voice (1:1, upserted) --------------------------------------------
class BrandVoiceUpsert(BaseModel):
    tone: str | None = Field(default=None, max_length=300)
    style_notes: str | None = None
    writing_sample: str | None = None
    do_list: list[str] = Field(default_factory=list)
    dont_list: list[str] = Field(default_factory=list)
    value_props: list[str] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)


class BrandVoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    tone: str | None = None
    style_notes: str | None = None
    writing_sample: str | None = None
    do_list: list[str] = []
    dont_list: list[str] = []
    value_props: list[str] = []
    vocabulary: list[str] = []


class BrandDetailOut(BrandOut):
    audiences: list[AudienceOut] = []
    personas: list[PersonaOut] = []
    voice: BrandVoiceOut | None = None

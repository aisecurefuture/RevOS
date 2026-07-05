"""Schemas for the Brand Book (Phase 3 M1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BrandBookUpdate(BaseModel):
    mission: str | None = None
    positioning: str | None = None
    elevator_pitch: str | None = None
    target_summary: str | None = None
    key_messages: list[str] | None = None
    banned_terms: list[str] | None = None
    required_disclaimers: list[str] | None = None
    compliance_notes: str | None = None
    competitors: list[str] | None = None
    is_published: bool | None = None


class BrandBookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    mission: str | None
    positioning: str | None
    elevator_pitch: str | None
    target_summary: str | None
    key_messages: list
    banned_terms: list
    required_disclaimers: list
    compliance_notes: str | None
    competitors: list
    is_published: bool


class ClaimCreate(BaseModel):
    claim: str = Field(min_length=1, max_length=500)
    proof: str | None = None
    category: str = Field(default="other", pattern="^(metric|certification|feature|testimonial|award|partnership|other)$")
    approved: bool = True
    expires_at: datetime | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim: str
    proof: str | None
    category: str
    approved: bool
    expires_at: datetime | None


class FactCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    category: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=500)


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic: str
    content: str
    category: str | None
    source: str | None


class CheckRequest(BaseModel):
    text: str = Field(min_length=1)
    require_disclaimers: bool = False


class CheckOut(BaseModel):
    passed: bool
    blocked: bool
    banned_hits: list[str]
    missing_disclaimers: list[str]
    unverified_numbers: list[str]


class GroundingOut(BaseModel):
    prompt_context: str
    approved_claims: list[str]
    banned_terms: list[str]
    required_disclaimers: list[str]
    is_published: bool

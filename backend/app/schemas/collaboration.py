"""Collaboration workspace schemas (CW1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.collaboration import CollaborationKind, CollaborationState


class CollaborationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_request_id: uuid.UUID
    brand_account_id: uuid.UUID
    creator_account_id: uuid.UUID
    creator_id: uuid.UUID
    product_id: uuid.UUID | None = None
    kind: CollaborationKind
    state: CollaborationState
    title: str | None = None
    ended_at: datetime | None = None
    created_at: datetime


class ShareBrandBookCreate(BaseModel):
    brand_id: uuid.UUID
    expires_at: datetime | None = None


class CollaborationShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collaboration_id: uuid.UUID
    shared_by_account_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    scope: str | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    status: str
    created_at: datetime


class SharedBrandBookOut(BaseModel):
    """The consumer view of a shared Brand Book — the fields useful to a
    collaborator (identity, messaging, and guardrails), not internal metadata."""

    model_config = ConfigDict(from_attributes=True)

    brand_id: uuid.UUID
    mission: str | None = None
    vision: str | None = None
    positioning: str | None = None
    elevator_pitch: str | None = None
    target_summary: str | None = None
    key_messages: list = Field(default_factory=list)
    core_values: list = Field(default_factory=list)
    brand_story: str | None = None
    voice_spectrum: dict = Field(default_factory=dict)
    banned_terms: list = Field(default_factory=list)
    required_disclaimers: list = Field(default_factory=list)
    is_published: bool = False


class OfferImportCreate(BaseModel):
    """Seed a marketplace product from an existing offer + marketplace fields."""

    offer_id: uuid.UUID
    industry: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=120)
    status: str | None = None
    discoverable: bool = False

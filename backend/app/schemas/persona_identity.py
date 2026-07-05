"""Schemas for persona identity + consent (Phase 3 M2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PersonaIdentityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand_id: uuid.UUID | None = None
    buyer_persona_id: uuid.UUID | None = None
    description: str | None = None
    appearance_notes: str | None = None
    voice_notes: str | None = None


class PersonaIdentityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    appearance_notes: str | None = None
    voice_notes: str | None = None
    buyer_persona_id: uuid.UUID | None = None


class PersonaIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None
    buyer_persona_id: uuid.UUID | None
    name: str
    description: str | None
    status: str
    appearance_notes: str | None
    voice_notes: str | None
    training_video_path: str | None
    voice_sample_path: str | None
    reference_image_paths: list
    voice_model_ref: str | None
    avatar_model_ref: str | None


class ConsentGrantRequest(BaseModel):
    subject_name: str = Field(min_length=1, max_length=200)
    subject_email: EmailStr
    consent_statement: str = Field(min_length=20)


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_name: str
    subject_email: str
    consent_statement: str
    policy_version: str
    granted_at: datetime | None
    revoked_at: datetime | None
    is_active: bool

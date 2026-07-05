"""Schemas for the viral video script engine (Phase 3 M4)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScriptGenerateRequest(BaseModel):
    brand_id: uuid.UUID
    target_seconds: int = Field(default=15)
    persona_identity_id: uuid.UUID | None = None
    angle: str | None = Field(default=None, max_length=500)


class ScriptUpdateRequest(BaseModel):
    script: str = Field(min_length=1, max_length=8000)


class VideoScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    persona_identity_id: uuid.UUID | None
    target_seconds: int
    angle: str | None
    script: str
    hook: str | None
    word_count: int
    passed_gate: bool
    gate: dict
    created_at: datetime

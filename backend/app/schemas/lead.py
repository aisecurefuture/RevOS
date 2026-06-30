"""Lead schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    company_name: str | None = None
    source: str | None = None
    consent_status: str
    lead_score: int
    confirmed_at: datetime | None = None
    created_at: datetime


class LeadDetailOut(LeadOut):
    tags: list[str] = []


class TagApply(BaseModel):
    tags: list[str] = Field(min_length=1)

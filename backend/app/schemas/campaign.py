"""Campaign schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.campaign import CampaignChannel, CampaignStatus


class CampaignCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=250)
    slug: str | None = Field(default=None, max_length=160)
    objective: str | None = Field(default=None, max_length=300)
    status: CampaignStatus = CampaignStatus.draft
    channel: CampaignChannel = CampaignChannel.email
    theme: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    budget_cents: int | None = Field(default=None, ge=0)
    offer_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    settings: dict = Field(default_factory=dict)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    objective: str | None = Field(default=None, max_length=300)
    status: CampaignStatus | None = None
    channel: CampaignChannel | None = None
    theme: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    budget_cents: int | None = Field(default=None, ge=0)
    offer_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    settings: dict | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    slug: str
    objective: str | None = None
    status: str
    channel: str
    theme: str | None = None
    utm_campaign: str | None = None
    budget_cents: int | None = None
    offer_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    settings: dict = {}
    created_at: datetime

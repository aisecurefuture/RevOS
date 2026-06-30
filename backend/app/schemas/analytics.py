"""Analytics schemas: revenue, UTM links, event tracking."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.analytics import RevenueStatus
from app.schemas.common import HttpUrlStr


class RevenueCreate(BaseModel):
    brand_id: uuid.UUID
    offer_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    amount_cents: int = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    source: str = Field(default="manual", max_length=40)
    status: RevenueStatus = RevenueStatus.paid
    occurred_at: datetime | None = None


class RevenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    offer_id: uuid.UUID | None = None
    amount_cents: int
    currency: str
    source: str
    status: str
    occurred_at: datetime | None = None


class UTMLinkCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    target_url: HttpUrlStr
    utm_source: str | None = Field(default=None, max_length=200)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    utm_term: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)


class UTMLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    target_url: str
    short_code: str
    click_count: int


class TrackEventRequest(BaseModel):
    brand_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    properties: dict = Field(default_factory=dict)
    utm: dict = Field(default_factory=dict)
    session_id: str | None = Field(default=None, max_length=80)

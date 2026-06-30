"""Offer schemas (polymorphic catalog: product/book/service/lead_magnet/…)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.offer import OfferStatus, OfferType
from app.schemas.common import HttpUrlStr


class OfferCreate(BaseModel):
    brand_id: uuid.UUID
    offer_type: OfferType = OfferType.product
    name: str = Field(min_length=1, max_length=250)
    slug: str | None = Field(default=None, max_length=160)
    subtitle: str | None = Field(default=None, max_length=300)
    description: str | None = None
    status: OfferStatus = OfferStatus.draft
    price_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stripe_price_id: str | None = Field(default=None, max_length=120)
    stripe_payment_link: HttpUrlStr | None = Field(default=None, max_length=500)
    external_url: HttpUrlStr | None = Field(default=None, max_length=500)
    asset_url: HttpUrlStr | None = Field(default=None, max_length=500)
    details: dict = Field(default_factory=dict)


class OfferUpdate(BaseModel):
    offer_type: OfferType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=250)
    subtitle: str | None = Field(default=None, max_length=300)
    description: str | None = None
    status: OfferStatus | None = None
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stripe_price_id: str | None = Field(default=None, max_length=120)
    stripe_payment_link: HttpUrlStr | None = Field(default=None, max_length=500)
    external_url: HttpUrlStr | None = Field(default=None, max_length=500)
    asset_url: HttpUrlStr | None = Field(default=None, max_length=500)
    details: dict | None = None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    offer_type: str
    name: str
    slug: str
    subtitle: str | None = None
    description: str | None = None
    status: str
    price_cents: int | None = None
    currency: str
    stripe_price_id: str | None = None
    stripe_payment_link: str | None = None
    external_url: str | None = None
    asset_url: str | None = None
    details: dict = {}
    created_at: datetime

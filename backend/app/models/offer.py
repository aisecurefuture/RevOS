"""Offers — the unified, polymorphic catalog.

Products, books, services, lead magnets, courses, and consulting offers are all
rows in one `offers` table discriminated by `offer_type`, with type-specific
detail in the `details` JSON blob. This is what lets you add a new product or
book without a schema change.
"""

from __future__ import annotations

import uuid
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, BaseModel


class OfferType(StrEnum):
    product = "product"
    book = "book"
    service = "service"
    lead_magnet = "lead_magnet"
    course = "course"
    consulting = "consulting"
    digital = "digital"


class OfferStatus(StrEnum):
    draft = "draft"
    active = "active"
    archived = "archived"


class Offer(BaseModel, table=True):
    __tablename__ = "offers"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    offer_type: OfferType = Field(default=OfferType.product, sa_type=sa.String, max_length=20)
    name: str = Field(index=True, max_length=250)
    slug: str = Field(index=True, max_length=160)
    subtitle: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, sa_type=sa.Text)
    status: OfferStatus = Field(default=OfferStatus.draft, sa_type=sa.String, max_length=20)

    # Commerce (Stripe-ready; all optional).
    price_cents: int | None = Field(default=None)
    currency: str = Field(default="USD", max_length=3)
    stripe_price_id: str | None = Field(default=None, max_length=120)
    stripe_payment_link: str | None = Field(default=None, max_length=500)
    external_url: str | None = Field(default=None, max_length=500)

    # Lead-magnet / digital delivery (asset gated behind opt-in).
    asset_path: str | None = Field(default=None, max_length=500)   # local/S3 key
    asset_url: str | None = Field(default=None, max_length=500)
    delivery_template_slug: str | None = Field(default=None, max_length=160)

    # Type-specific fields: book {isbn, retailers[]}, course {modules[]}, etc.
    details: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (sa.UniqueConstraint("brand_id", "slug", name="uq_offer_brand_slug"),)

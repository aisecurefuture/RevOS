"""Analytics & revenue intelligence: events, UTM links, goals, revenue."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel, utcnow


class RevenueStatus(StrEnum):
    pending = "pending"
    paid = "paid"
    refunded = "refunded"


class Event(TenantModel, table=True):
    """First-party, privacy-friendly event store.

    IP addresses are stored hashed (`ip_hash`), never raw, to keep analytics
    privacy-respecting.
    """

    __tablename__ = "events"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    name: str = Field(index=True, max_length=120)           # page_view, form_submit, email_open...
    entity_type: str | None = Field(default=None, max_length=60)
    entity_id: uuid.UUID | None = Field(default=None)
    lead_id: uuid.UUID | None = Field(default=None, foreign_key="leads.id", index=True)
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id", index=True)
    value_cents: int | None = Field(default=None)
    session_id: str | None = Field(default=None, max_length=80, index=True)
    ip_hash: str | None = Field(default=None, max_length=64)
    utm: dict = Field(default_factory=dict, sa_type=JSON)
    properties: dict = Field(default_factory=dict, sa_type=JSON)
    occurred_at: datetime = Field(default_factory=utcnow, index=True)


class UTMLink(TenantModel, table=True):
    """Tracked short link with embedded UTM parameters."""

    __tablename__ = "utm_links"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    created_by_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    name: str = Field(max_length=200)
    target_url: str = Field(max_length=1000)
    utm_source: str | None = Field(default=None, max_length=200)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    utm_term: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)
    short_code: str = Field(unique=True, index=True, max_length=40)
    click_count: int = Field(default=0)


class ConversionGoal(TenantModel, table=True):
    __tablename__ = "conversion_goals"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    name: str = Field(max_length=200)
    event_name: str = Field(max_length=120)
    value_cents: int | None = Field(default=None)
    funnel_stage: str | None = Field(default=None, max_length=80)
    target_count: int | None = Field(default=None)
    period: str | None = Field(default=None, max_length=20)     # month | quarter | year


class RevenueRecord(TenantModel, table=True):
    """A revenue event, attributable to an offer/deal/contact for ROI math."""

    __tablename__ = "revenue_records"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id", index=True)
    deal_id: uuid.UUID | None = Field(default=None, foreign_key="deals.id")
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id")
    amount_cents: int = Field(default=0)
    currency: str = Field(default="USD", max_length=3)
    source: str = Field(default="manual", max_length=40)        # stripe | deal | manual
    stripe_object_id: str | None = Field(default=None, index=True, max_length=200)
    status: RevenueStatus = Field(
        default=RevenueStatus.paid, sa_type=sa.String, max_length=12, index=True
    )
    occurred_at: datetime | None = Field(default=None, index=True)
    meta: dict = Field(default_factory=dict, sa_type=JSON)


class RevenueGoal(TenantModel, table=True):
    __tablename__ = "revenue_goals"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    name: str = Field(max_length=200)
    period: str = Field(default="month", max_length=20)
    target_cents: int = Field(default=0)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)

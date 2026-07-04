"""CRM-lite: companies, contacts, pipeline stages, deals, notes, tasks.

Contacts are the sales identities (this is where the LinkedIn export lands in
Module 9). Pipeline stages are *data*, not an enum, so you can reorder/rename
stages or add per-brand pipelines without a migration.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class LifecycleStage(StrEnum):
    subscriber = "subscriber"
    lead = "lead"
    mql = "mql"
    sql = "sql"
    opportunity = "opportunity"
    customer = "customer"
    evangelist = "evangelist"


class DealStatus(StrEnum):
    open = "open"
    won = "won"
    lost = "lost"


class TaskStatus(StrEnum):
    open = "open"
    done = "done"
    cancelled = "cancelled"


class Company(TenantModel, table=True):
    __tablename__ = "companies"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    name: str = Field(index=True, max_length=250)
    domain: str | None = Field(default=None, index=True, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=160)
    size: str | None = Field(default=None, max_length=60)              # e.g. "11-50"
    notes: str | None = Field(default=None, sa_type=sa.Text)
    custom_fields: dict = Field(default_factory=dict, sa_type=JSON)


class Contact(TenantModel, table=True):
    __tablename__ = "contacts"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    company_id: uuid.UUID | None = Field(default=None, foreign_key="companies.id", index=True)
    owner_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)

    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, index=True, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=200)
    linkedin_url: str | None = Field(default=None, max_length=400)

    source: str | None = Field(default=None, index=True, max_length=120)   # e.g. linkedin_import
    lifecycle_stage: LifecycleStage = Field(
        default=LifecycleStage.lead, sa_type=sa.String, max_length=20, index=True
    )
    lead_score: int = Field(default=0, index=True)
    custom_fields: dict = Field(default_factory=dict, sa_type=JSON)


class PipelineStage(TenantModel, table=True):
    """Ordered stages of a sales pipeline (seeded with the default 9)."""

    __tablename__ = "pipeline_stages"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    name: str = Field(max_length=120)
    slug: str = Field(index=True, max_length=80)
    order_index: int = Field(default=0)
    probability: int = Field(default=0)            # 0-100 win likelihood
    is_won: bool = Field(default=False)
    is_lost: bool = Field(default=False)

    __table_args__ = (
        sa.UniqueConstraint("brand_id", "slug", name="uq_stage_brand_slug"),
    )


class Deal(TenantModel, table=True):
    __tablename__ = "deals"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id", index=True)
    company_id: uuid.UUID | None = Field(default=None, foreign_key="companies.id", index=True)
    offer_id: uuid.UUID | None = Field(default=None, foreign_key="offers.id")
    pipeline_stage_id: uuid.UUID | None = Field(
        default=None, foreign_key="pipeline_stages.id", index=True
    )
    owner_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id", index=True)

    name: str = Field(max_length=250)
    amount_cents: int | None = Field(default=None)
    currency: str = Field(default="USD", max_length=3)
    status: DealStatus = Field(default=DealStatus.open, sa_type=sa.String, max_length=12, index=True)
    probability: int | None = Field(default=None)
    source: str | None = Field(default=None, max_length=120)
    expected_close_date: date | None = Field(default=None)
    closed_at: datetime | None = Field(default=None)
    custom_fields: dict = Field(default_factory=dict, sa_type=JSON)


class Note(TenantModel, table=True):
    """Free-form note attached to any entity (contact/company/deal/lead)."""

    __tablename__ = "notes"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    author_user_id: uuid.UUID | None = Field(default=None, foreign_key="admin_users.id")
    entity_type: str = Field(index=True, max_length=40)     # "contact" | "deal" | ...
    entity_id: uuid.UUID = Field(index=True)
    body: str = Field(sa_type=sa.Text)
    pinned: bool = Field(default=False)


class Task(TenantModel, table=True):
    """Follow-up task / reminder, optionally linked to a CRM entity."""

    __tablename__ = "tasks"

    brand_id: uuid.UUID | None = Field(default=None, foreign_key="brands.id", index=True)
    assignee_user_id: uuid.UUID | None = Field(
        default=None, foreign_key="admin_users.id", index=True
    )
    title: str = Field(max_length=250)
    description: str | None = Field(default=None, sa_type=sa.Text)
    status: TaskStatus = Field(default=TaskStatus.open, sa_type=sa.String, max_length=12, index=True)
    priority: int = Field(default=2)                        # 1 high .. 3 low
    entity_type: str | None = Field(default=None, max_length=40)
    entity_id: uuid.UUID | None = Field(default=None)
    due_at: datetime | None = Field(default=None, index=True)
    reminder_at: datetime | None = Field(default=None, index=True)
    completed_at: datetime | None = Field(default=None)

"""CRM schemas: contacts, companies, deals, pipeline, notes, tasks."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.crm import DealStatus, LifecycleStage, TaskStatus
from app.schemas.common import HttpUrlStr


# --- Company ----------------------------------------------------------------
class CompanyCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=250)
    domain: str | None = Field(default=None, max_length=200)
    website: HttpUrlStr | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=160)
    size: str | None = Field(default=None, max_length=60)
    notes: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    domain: str | None = Field(default=None, max_length=200)
    website: HttpUrlStr | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=160)
    size: str | None = Field(default=None, max_length=60)
    notes: str | None = None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    name: str
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    size: str | None = None
    created_at: datetime


# --- Contact ----------------------------------------------------------------
class ContactCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=200)
    linkedin_url: HttpUrlStr | None = Field(default=None, max_length=400)
    source: str | None = Field(default=None, max_length=120)
    lifecycle_stage: LifecycleStage = LifecycleStage.lead


class ContactUpdate(BaseModel):
    company_id: uuid.UUID | None = None
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    title: str | None = Field(default=None, max_length=200)
    linkedin_url: HttpUrlStr | None = Field(default=None, max_length=400)
    lifecycle_stage: LifecycleStage | None = None
    owner_user_id: uuid.UUID | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    linkedin_url: str | None = None
    source: str | None = None
    lifecycle_stage: str
    lead_score: int
    created_at: datetime


class ContactImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    companies_created: int
    note: str


# --- Pipeline / deals -------------------------------------------------------
class PipelineStageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID | None = None
    name: str
    slug: str
    order_index: int
    probability: int
    is_won: bool
    is_lost: bool


class DealCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=250)
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    offer_id: uuid.UUID | None = None
    pipeline_stage_id: uuid.UUID | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    source: str | None = Field(default=None, max_length=120)
    expected_close_date: date | None = None


class DealUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=250)
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    pipeline_stage_id: uuid.UUID | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    status: DealStatus | None = None
    expected_close_date: date | None = None


class DealMove(BaseModel):
    pipeline_stage_id: uuid.UUID


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    contact_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    pipeline_stage_id: uuid.UUID | None = None
    amount_cents: int | None = None
    currency: str
    status: str
    expected_close_date: date | None = None
    created_at: datetime


# --- Notes / tasks ----------------------------------------------------------
class NoteCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    entity_type: str = Field(min_length=1, max_length=40)
    entity_id: uuid.UUID
    body: str = Field(min_length=1)
    pinned: bool = False


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    body: str
    pinned: bool
    created_at: datetime


class TaskCreate(BaseModel):
    brand_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=250)
    description: str | None = None
    assignee_user_id: uuid.UUID | None = None
    entity_type: str | None = Field(default=None, max_length=40)
    entity_id: uuid.UUID | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: int = Field(default=2, ge=1, le=3)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = None
    status: TaskStatus | None = None
    assignee_user_id: uuid.UUID | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    priority: int | None = Field(default=None, ge=1, le=3)


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    status: str
    priority: int
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

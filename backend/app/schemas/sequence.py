"""Sequence, step, enrollment, and A/B schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.sequence import SequenceStatus, SequenceType


class ABVariant(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    subject: str = Field(min_length=1, max_length=400)
    weight: int = Field(default=1, ge=1, le=100)


class SequenceCreate(BaseModel):
    brand_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=160)
    sequence_type: SequenceType = SequenceType.custom
    description: str | None = None
    trigger: str = Field(default="manual", max_length=40)
    stop_on_goal: bool = True
    goal_event: str | None = Field(default=None, max_length=120)
    stop_on_reply: bool = True
    require_approval: bool = False


class SequenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    sequence_type: SequenceType | None = None
    trigger: str | None = Field(default=None, max_length=40)
    stop_on_goal: bool | None = None
    goal_event: str | None = Field(default=None, max_length=120)
    stop_on_reply: bool | None = None
    require_approval: bool | None = None
    status: SequenceStatus | None = None


class SequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    name: str
    slug: str
    sequence_type: str
    description: str | None = None
    status: str
    trigger: str
    stop_on_goal: bool
    goal_event: str | None = None
    require_approval: bool
    created_at: datetime


class StepCreate(BaseModel):
    name: str = Field(default="", max_length=200)
    order_index: int = Field(default=0, ge=0)
    delay_minutes: int = Field(default=1440, ge=0)
    subject: str | None = Field(default=None, max_length=400)
    html_body: str | None = None
    text_body: str | None = None
    template_id: uuid.UUID | None = None
    condition: dict = Field(default_factory=dict)
    require_approval: bool = False
    ab_variants: list[ABVariant] = Field(default_factory=list)


class StepUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    order_index: int | None = Field(default=None, ge=0)
    delay_minutes: int | None = Field(default=None, ge=0)
    subject: str | None = Field(default=None, max_length=400)
    html_body: str | None = None
    text_body: str | None = None
    condition: dict | None = None
    require_approval: bool | None = None
    is_active: bool | None = None


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_id: uuid.UUID
    name: str
    order_index: int
    delay_minutes: int
    subject: str | None = None
    require_approval: bool
    is_active: bool


class SequenceDetailOut(SequenceOut):
    steps: list[StepOut] = []


class EnrollRequest(BaseModel):
    lead_id: uuid.UUID


class EnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence_id: uuid.UUID
    lead_id: uuid.UUID | None = None
    status: str
    current_step_index: int
    next_run_at: datetime | None = None
    enrolled_at: datetime | None = None


class TickResult(BaseModel):
    processed: int
    sent: int
    completed: int
    awaiting_approval: int
    stopped: int


class GoalEvent(BaseModel):
    lead_id: uuid.UUID
    event_name: str = Field(min_length=1, max_length=120)

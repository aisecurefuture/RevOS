"""Email sequence engine models: sequences, steps, A/B tests, enrollments, runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class SequenceType(StrEnum):
    welcome = "welcome"
    book_launch = "book_launch"
    consulting_nurture = "consulting_nurture"
    cyberarmor_buyer = "cyberarmor_buyer"
    logistics_customer = "logistics_customer"
    founder_newsletter = "founder_newsletter"
    reengagement = "reengagement"
    abandoned_inquiry = "abandoned_inquiry"
    event_followup = "event_followup"
    custom = "custom"


class SequenceStatus(StrEnum):
    draft = "draft"
    active = "active"
    paused = "paused"
    archived = "archived"


class EnrollmentStatus(StrEnum):
    active = "active"
    paused = "paused"
    completed = "completed"
    stopped = "stopped"
    goal_met = "goal_met"
    unsubscribed = "unsubscribed"


class StepRunStatus(StrEnum):
    pending = "pending"
    pending_approval = "pending_approval"
    approved = "approved"
    scheduled = "scheduled"
    sent = "sent"
    skipped = "skipped"
    failed = "failed"


class Sequence(TenantModel, table=True):
    __tablename__ = "sequences"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    segment_id: uuid.UUID | None = Field(default=None, foreign_key="segments.id")
    name: str = Field(max_length=200)
    slug: str = Field(index=True, max_length=160)
    sequence_type: SequenceType = Field(
        default=SequenceType.custom, sa_type=sa.String, max_length=30
    )
    description: str | None = Field(default=None, sa_type=sa.Text)
    status: SequenceStatus = Field(
        default=SequenceStatus.draft, sa_type=sa.String, max_length=12, index=True
    )
    # How leads enter: form_submit | tag_added | manual | api
    trigger: str = Field(default="manual", max_length=40)
    # Stop conditions / goal tracking.
    stop_on_goal: bool = Field(default=True)
    goal_event: str | None = Field(default=None, max_length=120)
    stop_on_reply: bool = Field(default=True)
    # Approval-first: when true, each send waits for human approval.
    require_approval: bool = Field(default=False)
    settings: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (sa.UniqueConstraint("brand_id", "slug", name="uq_sequence_brand_slug"),)


class SequenceStep(TenantModel, table=True):
    __tablename__ = "sequence_steps"

    sequence_id: uuid.UUID = Field(foreign_key="sequences.id", index=True)
    template_id: uuid.UUID | None = Field(default=None, foreign_key="email_templates.id")
    order_index: int = Field(default=0)
    name: str = Field(default="", max_length=200)
    # Delay measured from the previous step's send (minutes).
    delay_minutes: int = Field(default=1440)
    subject: str | None = Field(default=None, max_length=400)
    html_body: str | None = Field(default=None, sa_type=sa.Text)
    text_body: str | None = Field(default=None, sa_type=sa.Text)
    # Optional per-step segment condition + send-window constraints.
    condition: dict = Field(default_factory=dict, sa_type=JSON)
    send_window: dict = Field(default_factory=dict, sa_type=JSON)
    require_approval: bool = Field(default=False)
    is_active: bool = Field(default=True)


class ABTest(TenantModel, table=True):
    """Subject-line (or variant) A/B test attached to a step or campaign."""

    __tablename__ = "ab_tests"

    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    sequence_step_id: uuid.UUID | None = Field(default=None, foreign_key="sequence_steps.id")
    campaign_id: uuid.UUID | None = Field(default=None, foreign_key="campaigns.id")
    name: str = Field(max_length=200)
    metric: str = Field(default="open", max_length=20)        # open | click
    # [{label, subject, weight}, ...]
    variants: list = Field(default_factory=list, sa_type=JSON)
    status: str = Field(default="draft", max_length=20)
    winner_variant: str | None = Field(default=None, max_length=40)


class Enrollment(TenantModel, table=True):
    """A lead's (or contact's) progress through a sequence."""

    __tablename__ = "enrollments"

    sequence_id: uuid.UUID = Field(foreign_key="sequences.id", index=True)
    brand_id: uuid.UUID = Field(foreign_key="brands.id", index=True)
    lead_id: uuid.UUID | None = Field(default=None, foreign_key="leads.id", index=True)
    contact_id: uuid.UUID | None = Field(default=None, foreign_key="contacts.id", index=True)

    status: EnrollmentStatus = Field(
        default=EnrollmentStatus.active, sa_type=sa.String, max_length=16, index=True
    )
    current_step_index: int = Field(default=0)
    next_run_at: datetime | None = Field(default=None, index=True)
    enrolled_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    paused_at: datetime | None = Field(default=None)
    stop_reason: str | None = Field(default=None, max_length=200)
    context: dict = Field(default_factory=dict, sa_type=JSON)

    __table_args__ = (
        sa.UniqueConstraint("sequence_id", "lead_id", name="uq_enrollment_seq_lead"),
    )


class StepRun(TenantModel, table=True):
    """A single scheduled/sent step for one enrollment."""

    __tablename__ = "step_runs"

    enrollment_id: uuid.UUID = Field(foreign_key="enrollments.id", index=True)
    sequence_step_id: uuid.UUID = Field(foreign_key="sequence_steps.id", index=True)
    status: StepRunStatus = Field(
        default=StepRunStatus.pending, sa_type=sa.String, max_length=20, index=True
    )
    scheduled_at: datetime | None = Field(default=None, index=True)
    sent_at: datetime | None = Field(default=None)
    # Plain reference (no FK) to avoid a circular dependency with email_messages,
    # which already carries the authoritative step_run_id FK back to this row.
    email_message_id: uuid.UUID | None = Field(default=None, index=True)
    variant_label: str | None = Field(default=None, max_length=40)
    error: str | None = Field(default=None, sa_type=sa.Text)

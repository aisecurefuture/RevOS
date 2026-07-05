"""Meeting scheduler — a self-hosted Calendly alternative (Phase 3).

An ``EventType`` is a bookable meeting definition owned by an account: duration,
buffers, booking window, location, and a weekly recurring availability
expressed in the host's IANA timezone (wall-clock). A ``Booking`` is one
scheduled meeting created by a public invitee.

Timezone model: availability windows are wall-clock local time in
``EventType.timezone``; ``Booking.start_at``/``end_at`` are naive UTC instants
(the codebase convention). Slot generation converts wall-clock → UTC per date,
so DST transitions are honored. ``blocked_*`` snapshot the buffer-expanded
interval so conflict checks are a plain overlap.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import JSON, TenantModel


class LocationType(StrEnum):
    custom = "custom"        # a link or instructions the host provides (e.g. a Zoom URL)
    phone = "phone"          # host calls the invitee, or vice versa
    in_person = "in_person"  # a physical address


class BookingStatus(StrEnum):
    confirmed = "confirmed"
    cancelled = "cancelled"


class EventType(TenantModel, table=True):
    __tablename__ = "scheduler_event_types"

    created_by: uuid.UUID = Field(foreign_key="admin_users.id", index=True)
    name: str = Field(max_length=200)
    slug: str = Field(max_length=140, index=True)
    description: str | None = Field(default=None, sa_type=sa.Text)

    duration_minutes: int = Field(default=30)
    buffer_before_minutes: int = Field(default=0)
    buffer_after_minutes: int = Field(default=0)
    # Booking window guards.
    min_notice_minutes: int = Field(default=240)     # earliest bookable = now + this
    max_days_ahead: int = Field(default=60)          # latest bookable date

    timezone: str = Field(default="UTC", max_length=64)  # IANA, host's zone
    # [{"weekday": 0-6 (Mon=0), "start": "HH:MM", "end": "HH:MM"}, ...]
    weekly_availability: list = Field(default_factory=list, sa_type=JSON)

    location_type: LocationType = Field(default=LocationType.custom, sa_type=sa.String(16))
    location_detail: str | None = Field(default=None, max_length=500)

    active: bool = Field(default=True, index=True)


class Booking(TenantModel, table=True):
    __tablename__ = "scheduler_bookings"
    __table_args__ = (
        # Hard guarantee against concurrent double-booking of the same discrete
        # slot. Partial (confirmed-only) so a cancelled slot reopens for booking.
        sa.Index(
            "uq_booking_confirmed_slot",
            "event_type_id", "start_at",
            unique=True,
            sqlite_where=sa.text("status = 'confirmed'"),
            postgresql_where=sa.text("status = 'confirmed'"),
        ),
    )

    event_type_id: uuid.UUID = Field(foreign_key="scheduler_event_types.id", index=True)

    invitee_name: str = Field(max_length=200)
    invitee_email: str = Field(max_length=320, index=True)
    invitee_timezone: str = Field(default="UTC", max_length=64)
    invitee_notes: str | None = Field(default=None, sa_type=sa.Text)

    start_at: datetime = Field(index=True)   # naive UTC
    end_at: datetime                          # naive UTC
    # Buffer-expanded interval (start - buffer_before, end + buffer_after),
    # snapshot at booking time so conflict checks are a simple overlap.
    blocked_start_at: datetime = Field(index=True)
    blocked_end_at: datetime = Field(index=True)

    status: BookingStatus = Field(default=BookingStatus.confirmed, sa_type=sa.String(12), index=True)
    location_type: LocationType = Field(default=LocationType.custom, sa_type=sa.String(16))
    location_detail: str | None = Field(default=None, max_length=500)

    # Unguessable token for the public cancel / reschedule links.
    manage_token: str = Field(max_length=64, index=True)
    cancelled_at: datetime | None = Field(default=None)

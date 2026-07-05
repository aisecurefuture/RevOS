"""Schemas for the meeting scheduler (Phase 3)."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AvailabilityWindow(BaseModel):
    weekday: int = Field(ge=0, le=6)  # Mon=0 .. Sun=6
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def _valid_hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("Time must be HH:MM (24-hour).")
        return v


def _validate_tz(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone '{v}'.") from exc
    return v


class EventTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=140)
    description: str | None = None
    duration_minutes: int = Field(default=30, ge=5, le=8 * 60)
    buffer_before_minutes: int = Field(default=0, ge=0, le=8 * 60)
    buffer_after_minutes: int = Field(default=0, ge=0, le=8 * 60)
    min_notice_minutes: int = Field(default=240, ge=0, le=90 * 24 * 60)
    max_days_ahead: int = Field(default=60, ge=1, le=365)
    timezone: str = "UTC"
    weekly_availability: list[AvailabilityWindow] = Field(default_factory=list)
    location_type: str = Field(default="custom", pattern="^(custom|phone|in_person)$")
    location_detail: str | None = Field(default=None, max_length=500)
    active: bool = True

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return _validate_tz(v)

    @field_validator("slug")
    @classmethod
    def _slug_fmt(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG.match(v):
            raise ValueError("Slug may contain only lowercase letters, numbers, and hyphens.")
        return v

    @field_validator("weekly_availability")
    @classmethod
    def _windows_ordered(cls, v: list[AvailabilityWindow]) -> list[AvailabilityWindow]:
        for w in v:
            if w.end <= w.start:
                raise ValueError("Each availability window must end after it starts.")
        return v


class EventTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=8 * 60)
    buffer_before_minutes: int | None = Field(default=None, ge=0, le=8 * 60)
    buffer_after_minutes: int | None = Field(default=None, ge=0, le=8 * 60)
    min_notice_minutes: int | None = Field(default=None, ge=0, le=90 * 24 * 60)
    max_days_ahead: int | None = Field(default=None, ge=1, le=365)
    timezone: str | None = None
    weekly_availability: list[AvailabilityWindow] | None = None
    location_type: str | None = Field(default=None, pattern="^(custom|phone|in_person)$")
    location_detail: str | None = Field(default=None, max_length=500)
    active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        return _validate_tz(v) if v is not None else v


class EventTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    min_notice_minutes: int
    max_days_ahead: int
    timezone: str
    weekly_availability: list
    location_type: str
    location_detail: str | None
    active: bool


class PublicEventTypeOut(BaseModel):
    """What a public invitee sees on the booking page (no internal IDs beyond
    the event type, no host email)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    duration_minutes: int
    timezone: str
    location_type: str


class BookRequest(BaseModel):
    start_at: datetime
    invitee_name: str = Field(min_length=1, max_length=200)
    invitee_email: EmailStr
    invitee_timezone: str = "UTC"
    invitee_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("start_at")
    @classmethod
    def _naive_utc(cls, v: datetime) -> datetime:
        # Normalize to naive UTC so it can be compared against stored slots.
        if v.tzinfo is not None:
            return v.astimezone(UTC).replace(tzinfo=None)
        return v

    @field_validator("invitee_timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return _validate_tz(v)


class RescheduleRequest(BaseModel):
    start_at: datetime

    @field_validator("start_at")
    @classmethod
    def _naive_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            return v.astimezone(UTC).replace(tzinfo=None)
        return v


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type_id: uuid.UUID
    invitee_name: str
    invitee_email: str
    invitee_timezone: str
    invitee_notes: str | None
    start_at: datetime
    end_at: datetime
    status: str
    location_type: str
    location_detail: str | None


class PublicBookingOut(BaseModel):
    """Confirmation view for a public invitee (includes the manage token so the
    UI can render reschedule/cancel; the token is already in their URL)."""
    model_config = ConfigDict(from_attributes=True)

    event_type_id: uuid.UUID
    invitee_name: str
    invitee_email: str
    invitee_timezone: str
    start_at: datetime
    end_at: datetime
    status: str
    location_type: str
    location_detail: str | None
    manage_token: str


class SlotsOut(BaseModel):
    timezone: str            # the host timezone the event is defined in
    duration_minutes: int
    slots: list[datetime]    # naive-UTC slot starts; the client renders in the invitee's zone

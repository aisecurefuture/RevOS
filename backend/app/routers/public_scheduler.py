"""Meeting scheduler — public booking surface (Phase 3).

Unauthenticated, rate-limited. Invitees view an event type, fetch open slots,
book, and cancel/reschedule via an unguessable ``manage_token``. Writes are
bound to the event type's account via the tenancy context so rows land in the
right workspace despite there being no session.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request

from app.core.exceptions import RevOSError
from app.core.rate_limit import rate_limit
from app.core.tenancy import set_active_account
from app.deps import DbSession
from app.models.base import utcnow
from app.schemas.scheduler import (
    BookRequest,
    PublicBookingOut,
    PublicEventTypeOut,
    RescheduleRequest,
    SlotsOut,
)
from app.services import scheduler_service as svc

router = APIRouter(prefix="/public/scheduler", tags=["public-scheduler"])

_slots_limit = rate_limit("scheduler_slots", "120/minute")
_book_limit = rate_limit("scheduler_book", "10/minute")


@router.get("/event/{event_type_id}", response_model=PublicEventTypeOut)
async def get_event(
    event_type_id: uuid.UUID, db: DbSession, _rl: None = Depends(_slots_limit),
) -> PublicEventTypeOut:
    et = await svc.get_public_event_type(db, event_type_id)
    return PublicEventTypeOut.model_validate(et)


@router.get("/event/{event_type_id}/slots", response_model=SlotsOut)
async def get_slots(
    event_type_id: uuid.UUID,
    db: DbSession,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    _rl: None = Depends(_slots_limit),
) -> SlotsOut:
    et = await svc.get_public_event_type(db, event_type_id)
    # Never generate slots for the past; clamp the window start to today.
    today = utcnow().date()
    if from_date < today:
        from_date = today
    if to_date < from_date:
        to_date = from_date
    slots = await svc.available_slots(db, et, from_date, to_date)
    return SlotsOut(timezone=et.timezone, duration_minutes=et.duration_minutes, slots=slots)


@router.post("/event/{event_type_id}/book", response_model=PublicBookingOut, status_code=201)
async def book(
    event_type_id: uuid.UUID, body: BookRequest, db: DbSession,
    _rl: None = Depends(_book_limit),
) -> PublicBookingOut:
    et = await svc.get_public_event_type(db, event_type_id)
    set_active_account(et.account_id)  # bind the no-auth write to the host's account
    booking = await svc.book_slot(
        db, et,
        start_at=body.start_at,
        invitee_name=body.invitee_name,
        invitee_email=str(body.invitee_email),
        invitee_timezone=body.invitee_timezone,
        invitee_notes=body.invitee_notes,
    )
    return PublicBookingOut.model_validate(booking)


@router.get("/booking/{manage_token}", response_model=PublicBookingOut)
async def get_booking(
    manage_token: str, db: DbSession, _rl: None = Depends(_slots_limit),
) -> PublicBookingOut:
    booking = await svc.get_booking_by_token(db, manage_token)
    return PublicBookingOut.model_validate(booking)


@router.post("/booking/{manage_token}/cancel", response_model=PublicBookingOut)
async def cancel(
    manage_token: str, db: DbSession, _rl: None = Depends(_book_limit),
) -> PublicBookingOut:
    booking = await svc.get_booking_by_token(db, manage_token)
    set_active_account(booking.account_id)
    booking = await svc.cancel_booking(db, booking)
    return PublicBookingOut.model_validate(booking)


@router.post("/booking/{manage_token}/reschedule", response_model=PublicBookingOut)
async def reschedule(
    manage_token: str, body: RescheduleRequest, db: DbSession,
    _rl: None = Depends(_book_limit),
) -> PublicBookingOut:
    booking = await svc.get_booking_by_token(db, manage_token)
    set_active_account(booking.account_id)
    new_booking = await svc.reschedule_booking(db, booking, body.start_at)
    return PublicBookingOut.model_validate(new_booking)

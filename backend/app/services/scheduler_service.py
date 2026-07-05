"""Meeting scheduler service (Phase 3) — availability, slots, bookings.

The correctness core lives here:

* **Timezone-safe slot generation.** Availability is wall-clock in the host's
  IANA zone; each candidate slot's wall-clock start on a given date is converted
  to a UTC instant via ``zoneinfo``, so DST shifts land on the right absolute
  time.
* **Conflict avoidance.** A candidate is rejected if its buffer-expanded
  interval overlaps any confirmed booking's buffer-expanded interval on the
  same account, or if it falls outside the [min-notice, max-days-ahead] window.
* **Double-booking races.** ``book_slot`` re-validates against live availability
  inside the transaction and relies on the partial unique index
  ``uq_booking_confirmed_slot`` to make two simultaneous bookings of the same
  slot impossible — the loser gets a clean 409.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ConflictError, NotFoundError, RevOSError
from app.models.base import utcnow
from app.models.scheduler import Booking, BookingStatus, EventType, LocationType
from app.models.user import AdminUser
from app.services.transactional_email import send_transactional

logger = logging.getLogger("revos.scheduler")

_MAX_RANGE_DAYS = 62  # cap a single slots query so it can't fan out unbounded


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise RevOSError(f"Unknown timezone '{tz}'.", code="invalid_timezone", status_code=400) from exc


def _to_utc_naive(local_dt: datetime, tz: ZoneInfo) -> datetime:
    """Interpret ``local_dt`` (naive wall-clock) as being in ``tz`` and return
    the equivalent naive UTC instant."""
    from datetime import UTC
    return local_dt.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None)


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


# ---------------------------------------------------------------------------
# Conflict logic
# ---------------------------------------------------------------------------

def _intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """True if [a_start, a_end) and [b_start, b_end) overlap (touching endpoints
    do not count as a conflict — a slot may start exactly when another ends)."""
    return a_start < b_end and b_start < a_end


# ---------------------------------------------------------------------------
# Slot generation
# ---------------------------------------------------------------------------

async def available_slots(
    db: AsyncSession,
    event_type: EventType,
    from_date: date,
    to_date: date,
) -> list[datetime]:
    """Return the list of open slot start instants (naive UTC) for an event type
    across [from_date, to_date] inclusive (dates interpreted in the host zone)."""
    if (to_date - from_date).days > _MAX_RANGE_DAYS:
        raise RevOSError("Date range too large.", code="range_too_large", status_code=400)

    tz = _zone(event_type.timezone)
    now = utcnow()
    earliest = now + timedelta(minutes=event_type.min_notice_minutes)
    latest = now + timedelta(days=event_type.max_days_ahead)

    duration = timedelta(minutes=event_type.duration_minutes)
    buf_before = timedelta(minutes=event_type.buffer_before_minutes)
    buf_after = timedelta(minutes=event_type.buffer_after_minutes)

    # Availability windows grouped by weekday (Mon=0).
    windows_by_weekday: dict[int, list[tuple[time, time]]] = {}
    for w in event_type.weekly_availability:
        try:
            weekday = int(w["weekday"])
            start_t = _parse_hhmm(w["start"])
            end_t = _parse_hhmm(w["end"])
        except (KeyError, ValueError, TypeError):
            continue
        if not (0 <= weekday <= 6) or end_t <= start_t:
            continue
        windows_by_weekday.setdefault(weekday, []).append((start_t, end_t))

    if not windows_by_weekday:
        return []

    # Pull confirmed bookings that could conflict in the window (+ a day margin
    # on each side to catch buffer-straddling bookings).
    range_start_utc = _to_utc_naive(datetime.combine(from_date - timedelta(days=1), time.min), tz)
    range_end_utc = _to_utc_naive(datetime.combine(to_date + timedelta(days=2), time.min), tz)
    existing = await _confirmed_bookings_in_range(
        db, event_type.account_id, range_start_utc, range_end_utc,
    )

    slots: list[datetime] = []
    day = from_date
    while day <= to_date:
        for start_t, end_t in windows_by_weekday.get(day.weekday(), []):
            window_start = datetime.combine(day, start_t)
            window_end = datetime.combine(day, end_t)
            cursor = window_start
            while cursor + duration <= window_end:
                slot_start = _to_utc_naive(cursor, tz)
                slot_end = slot_start + duration
                cursor += duration  # advance before any continue

                if slot_start < earliest or slot_start > latest:
                    continue

                blocked_start = slot_start - buf_before
                blocked_end = slot_end + buf_after
                if any(
                    _intervals_overlap(blocked_start, blocked_end, b.blocked_start_at, b.blocked_end_at)
                    for b in existing
                ):
                    continue
                slots.append(slot_start)
        day += timedelta(days=1)

    return slots


async def _confirmed_bookings_in_range(
    db: AsyncSession, account_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> list[Booking]:
    result = await db.execute(
        select(Booking).where(
            Booking.account_id == account_id,
            Booking.status == BookingStatus.confirmed,
            Booking.deleted_at.is_(None),
            Booking.blocked_end_at > start_utc,
            Booking.blocked_start_at < end_utc,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Event type CRUD
# ---------------------------------------------------------------------------

async def get_event_type(db: AsyncSession, event_type_id: uuid.UUID) -> EventType:
    result = await db.execute(
        select(EventType).where(
            EventType.id == event_type_id,
            EventType.deleted_at.is_(None),
        )
    )
    et = result.scalar_one_or_none()
    if et is None:
        raise NotFoundError("Event type not found.")
    return et


async def get_public_event_type(db: AsyncSession, event_type_id: uuid.UUID) -> EventType:
    et = await get_event_type(db, event_type_id)
    if not et.active:
        raise NotFoundError("This scheduling link is not available.")
    return et


async def list_event_types(db: AsyncSession, account_id: uuid.UUID) -> list[EventType]:
    result = await db.execute(
        select(EventType).where(
            EventType.account_id == account_id,
            EventType.deleted_at.is_(None),
        ).order_by(EventType.created_at.desc())
    )
    return list(result.scalars().all())


async def create_event_type(db: AsyncSession, account_id: uuid.UUID, user: AdminUser, data: dict) -> EventType:
    _zone(data.get("timezone", "UTC"))  # validate tz up front
    et = EventType(account_id=account_id, created_by=user.id, **data)
    db.add(et)
    await db.flush()
    await db.refresh(et)
    return et


async def update_event_type(db: AsyncSession, event_type_id: uuid.UUID, account_id: uuid.UUID, data: dict) -> EventType:
    et = await get_event_type(db, event_type_id)
    if et.account_id != account_id:
        raise NotFoundError("Event type not found.")
    if "timezone" in data:
        _zone(data["timezone"])
    for key, value in data.items():
        setattr(et, key, value)
    db.add(et)
    await db.flush()
    await db.refresh(et)
    return et


async def delete_event_type(db: AsyncSession, event_type_id: uuid.UUID, account_id: uuid.UUID) -> None:
    et = await get_event_type(db, event_type_id)
    if et.account_id != account_id:
        raise NotFoundError("Event type not found.")
    et.deleted_at = utcnow()
    et.active = False
    db.add(et)
    await db.flush()


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

async def book_slot(
    db: AsyncSession,
    event_type: EventType,
    *,
    start_at: datetime,
    invitee_name: str,
    invitee_email: str,
    invitee_timezone: str,
    invitee_notes: str | None,
) -> Booking:
    """Create a confirmed booking for a specific UTC slot.

    Re-validates the slot against live availability inside the transaction, then
    inserts — the partial unique index makes a concurrent duplicate impossible
    (the loser raises IntegrityError → 409)."""
    # start_at must be one of the currently-open slots for its date. Recomputing
    # for that single host-local day is cheap and closes the "book any time"
    # hole a naive endpoint would leave open.
    tz = _zone(event_type.timezone)
    from datetime import UTC
    local_day = start_at.replace(tzinfo=UTC).astimezone(tz).date()
    open_slots = await available_slots(db, event_type, local_day, local_day)
    if start_at not in open_slots:
        raise ConflictError("That time is no longer available. Please pick another slot.")

    duration = timedelta(minutes=event_type.duration_minutes)
    end_at = start_at + duration
    booking = Booking(
        account_id=event_type.account_id,
        event_type_id=event_type.id,
        invitee_name=invitee_name.strip(),
        invitee_email=invitee_email.strip().lower(),
        invitee_timezone=invitee_timezone,
        invitee_notes=invitee_notes,
        start_at=start_at,
        end_at=end_at,
        blocked_start_at=start_at - timedelta(minutes=event_type.buffer_before_minutes),
        blocked_end_at=end_at + timedelta(minutes=event_type.buffer_after_minutes),
        status=BookingStatus.confirmed,
        location_type=event_type.location_type,
        location_detail=event_type.location_detail,
        manage_token=secrets.token_urlsafe(32),
    )
    db.add(booking)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("That time was just booked by someone else. Please pick another slot.") from exc
    await db.refresh(booking)

    await _notify_booked(db, event_type, booking)
    return booking


async def get_booking_by_token(db: AsyncSession, manage_token: str) -> Booking:
    result = await db.execute(
        select(Booking).where(
            Booking.manage_token == manage_token,
            Booking.deleted_at.is_(None),
        )
    )
    booking = result.scalar_one_or_none()
    if booking is None:
        raise NotFoundError("Booking not found.")
    return booking


async def cancel_booking(db: AsyncSession, booking: Booking) -> Booking:
    if booking.status == BookingStatus.cancelled:
        return booking
    booking.status = BookingStatus.cancelled
    booking.cancelled_at = utcnow()
    db.add(booking)
    await db.flush()
    et = await get_event_type(db, booking.event_type_id)
    await _notify_cancelled(et, booking)
    return booking


async def reschedule_booking(db: AsyncSession, booking: Booking, new_start_at: datetime) -> Booking:
    """Cancel the existing booking and create a fresh one at the new time."""
    if booking.status != BookingStatus.confirmed:
        raise ConflictError("This booking can no longer be rescheduled.")
    event_type = await get_event_type(db, booking.event_type_id)
    # Free the old slot first so a same-slot reschedule doesn't self-conflict on
    # the partial unique index.
    booking.status = BookingStatus.cancelled
    booking.cancelled_at = utcnow()
    db.add(booking)
    await db.flush()
    return await book_slot(
        db, event_type,
        start_at=new_start_at,
        invitee_name=booking.invitee_name,
        invitee_email=booking.invitee_email,
        invitee_timezone=booking.invitee_timezone,
        invitee_notes=booking.invitee_notes,
    )


async def list_bookings(
    db: AsyncSession, account_id: uuid.UUID, *, upcoming_only: bool = False
) -> list[Booking]:
    filters = [Booking.account_id == account_id, Booking.deleted_at.is_(None)]
    if upcoming_only:
        filters.append(Booking.start_at >= utcnow())
        filters.append(Booking.status == BookingStatus.confirmed)
    result = await db.execute(
        select(Booking).where(*filters).order_by(Booking.start_at.asc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Notifications (best-effort)
# ---------------------------------------------------------------------------

def _fmt_local(dt: datetime, tz_name: str) -> str:
    from datetime import UTC
    try:
        local = dt.replace(tzinfo=UTC).astimezone(_zone(tz_name))
    except RevOSError:
        local = dt.replace(tzinfo=UTC)
    return local.strftime("%A, %B %d, %Y at %I:%M %p %Z")


async def _notify_booked(db: AsyncSession, event_type: EventType, booking: Booking) -> None:
    manage_url = f"{settings.frontend_base_url}/booking/{booking.manage_token}"
    when_invitee = _fmt_local(booking.start_at, booking.invitee_timezone)
    when_host = _fmt_local(booking.start_at, event_type.timezone)
    loc = booking.location_detail or booking.location_type
    try:
        send_transactional(
            to_email=booking.invitee_email,
            subject=f"Confirmed: {event_type.name} — {when_invitee}",
            html=(
                f"<p>Hi {booking.invitee_name},</p>"
                f"<p>Your <strong>{event_type.name}</strong> is confirmed for "
                f"<strong>{when_invitee}</strong>.</p>"
                f"<p>Location: {loc}</p>"
                f'<p><a href="{manage_url}">Reschedule or cancel</a></p>'
            ),
            text=f"Confirmed: {event_type.name} for {when_invitee}. Manage: {manage_url}",
        )
    except Exception:  # noqa: BLE001 — email failure must not fail the booking
        logger.exception("Failed to send booking confirmation to %s", booking.invitee_email)

    # Notify the host.
    host = await db.get(AdminUser, event_type.created_by)
    if host is not None:
        try:
            send_transactional(
                to_email=host.email,
                subject=f"New booking: {event_type.name} with {booking.invitee_name}",
                html=(
                    f"<p>{booking.invitee_name} ({booking.invitee_email}) booked "
                    f"<strong>{event_type.name}</strong>.</p>"
                    f"<p>When: <strong>{when_host}</strong></p>"
                    + (f"<p>Notes: {booking.invitee_notes}</p>" if booking.invitee_notes else "")
                ),
                text=f"{booking.invitee_name} booked {event_type.name} for {when_host}.",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send host booking notification to %s", host.email)


async def _notify_cancelled(event_type: EventType, booking: Booking) -> None:
    when = _fmt_local(booking.start_at, booking.invitee_timezone)
    try:
        send_transactional(
            to_email=booking.invitee_email,
            subject=f"Cancelled: {event_type.name} — {when}",
            html=(
                f"<p>Hi {booking.invitee_name},</p>"
                f"<p>Your <strong>{event_type.name}</strong> on {when} has been cancelled.</p>"
            ),
            text=f"Cancelled: {event_type.name} on {when}.",
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send cancellation to %s", booking.invitee_email)

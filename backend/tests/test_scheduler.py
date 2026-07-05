"""Meeting scheduler (Phase 3).

Focus on the correctness core: timezone/DST-safe slot generation, notice and
horizon windows, buffer-aware conflicts, the full public booking lifecycle, and
the double-booking guarantee (both the re-validation path and the DB unique
index).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.base import utcnow
from app.models.scheduler import Booking, BookingStatus, EventType
from app.services import scheduler_service as svc


def _et(**overrides) -> EventType:
    """An in-memory event type (not persisted) for pure slot-gen tests."""
    base = dict(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        name="Intro call",
        slug="intro",
        duration_minutes=30,
        buffer_before_minutes=0,
        buffer_after_minutes=0,
        min_notice_minutes=0,
        max_days_ahead=365,
        timezone="UTC",
        weekly_availability=[{"weekday": d, "start": "09:00", "end": "17:00"} for d in range(7)],
        location_type="custom",
        active=True,
    )
    base.update(overrides)
    return EventType(**base)


# ---------------------------------------------------------------------------
# Timezone / DST correctness (the reason this module needs care)
# ---------------------------------------------------------------------------

def test_to_utc_naive_handles_dst():
    ny = ZoneInfo("America/New_York")
    # Winter: EST = UTC-5 → 09:00 local is 14:00 UTC.
    assert svc._to_utc_naive(datetime(2026, 1, 15, 9, 0), ny) == datetime(2026, 1, 15, 14, 0)
    # Summer: EDT = UTC-4 → 09:00 local is 13:00 UTC.
    assert svc._to_utc_naive(datetime(2026, 7, 15, 9, 0), ny) == datetime(2026, 7, 15, 13, 0)


@pytest.mark.asyncio
async def test_slots_reflect_host_local_walltime_across_zones(async_session_factory):
    """Every generated slot, converted back to the host zone, must be at the
    availability wall-clock time — regardless of the zone's UTC offset / DST."""
    et = _et(timezone="America/New_York", duration_minutes=60,
             weekly_availability=[{"weekday": d, "start": "09:00", "end": "10:00"} for d in range(7)])
    target = utcnow().date() + timedelta(days=10)
    async with async_session_factory() as s:
        slots = await svc.available_slots(s, et, target, target)
    assert len(slots) == 1
    back = slots[0].replace(tzinfo=UTC).astimezone(ZoneInfo("America/New_York"))
    assert (back.hour, back.minute) == (9, 0)


# ---------------------------------------------------------------------------
# Slot generation windows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slots_count_within_window(async_session_factory):
    et = _et(duration_minutes=30)  # 09:00–17:00 → 16 slots/day
    day = utcnow().date() + timedelta(days=3)
    async with async_session_factory() as s:
        slots = await svc.available_slots(s, et, day, day)
    assert len(slots) == 16
    assert slots[0] == datetime.combine(day, datetime.min.time()).replace(hour=9)
    assert slots[-1] == datetime.combine(day, datetime.min.time()).replace(hour=16, minute=30)


@pytest.mark.asyncio
async def test_min_notice_excludes_near_slots(async_session_factory):
    # A 48h notice on an all-day-available event: today has no bookable slots.
    et = _et(min_notice_minutes=48 * 60)
    today = utcnow().date()
    async with async_session_factory() as s:
        slots = await svc.available_slots(s, et, today, today)
    assert slots == []


@pytest.mark.asyncio
async def test_max_days_ahead_excludes_far_slots(async_session_factory):
    et = _et(max_days_ahead=7)
    far = utcnow().date() + timedelta(days=20)
    async with async_session_factory() as s:
        slots = await svc.available_slots(s, et, far, far)
    assert slots == []


@pytest.mark.asyncio
async def test_no_availability_on_that_weekday(async_session_factory):
    day = utcnow().date() + timedelta(days=3)
    # Only make the *other* six weekdays available.
    avail = [{"weekday": d, "start": "09:00", "end": "17:00"} for d in range(7) if d != day.weekday()]
    et = _et(weekly_availability=avail)
    async with async_session_factory() as s:
        slots = await svc.available_slots(s, et, day, day)
    assert slots == []


# ---------------------------------------------------------------------------
# Buffer-aware conflicts against existing bookings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_existing_booking_blocks_overlapping_and_buffered_slots(async_session_factory):
    account_id = uuid.uuid4()
    et = _et(account_id=account_id, duration_minutes=30, buffer_after_minutes=15)
    day = utcnow().date() + timedelta(days=3)
    slot_10 = datetime.combine(day, datetime.min.time()).replace(hour=10)  # 10:00–10:30

    async with async_session_factory() as s:
        # A confirmed booking 10:00–10:30 with a 15m after-buffer blocks through 10:45.
        s.add(Booking(
            account_id=account_id, event_type_id=et.id,
            invitee_name="X", invitee_email="x@e.com", invitee_timezone="UTC",
            start_at=slot_10, end_at=slot_10 + timedelta(minutes=30),
            blocked_start_at=slot_10, blocked_end_at=slot_10 + timedelta(minutes=45),
            status=BookingStatus.confirmed, manage_token="tok",
        ))
        await s.commit()

        slots = await svc.available_slots(s, et, day, day)

    starts = {sl.hour * 60 + sl.minute for sl in slots}
    assert 9 * 60 in starts               # 09:00 (ends 09:30, buffer to 09:45 — clear)
    assert 9 * 60 + 30 not in starts      # 09:30 ends 10:00; its +15 buffer hits the booking
    assert 10 * 60 not in starts          # 10:00 taken
    assert 10 * 60 + 30 not in starts     # 10:30 falls inside the booking's after-buffer
    assert 11 * 60 in starts              # 11:00 is clear again


# ---------------------------------------------------------------------------
# DB double-booking guarantee (partial unique index)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unique_index_blocks_two_confirmed_same_slot(async_session_factory):
    account_id, et_id = uuid.uuid4(), uuid.uuid4()
    start = utcnow().replace(microsecond=0) + timedelta(days=3)

    def _bk(email, status=BookingStatus.confirmed, token="t"):
        return Booking(
            account_id=account_id, event_type_id=et_id,
            invitee_name="X", invitee_email=email, invitee_timezone="UTC",
            start_at=start, end_at=start + timedelta(minutes=30),
            blocked_start_at=start, blocked_end_at=start + timedelta(minutes=30),
            status=status, manage_token=token,
        )

    async with async_session_factory() as s:
        s.add(_bk("a@e.com", token="t1"))
        await s.flush()
        s.add(_bk("b@e.com", token="t2"))
        with pytest.raises(IntegrityError):
            await s.flush()

    # A cancelled booking at the same slot does NOT block a new confirmed one
    # (partial index is confirmed-only).
    async with async_session_factory() as s:
        s.add(_bk("c@e.com", status=BookingStatus.cancelled, token="t3"))
        await s.flush()
        s.add(_bk("d@e.com", token="t4"))
        await s.flush()  # must not raise


# ---------------------------------------------------------------------------
# Full public lifecycle through the API
# ---------------------------------------------------------------------------

async def _register_owner(api):
    r = await api.post("/api/auth/register", json={
        "email": "host@test.com", "password": "OwnerPass123", "full_name": "Host",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _create_event_type(api, headers):
    r = await api.post("/api/scheduler/event-types", headers=headers, json={
        "name": "Intro Call", "slug": "intro", "duration_minutes": 30,
        "min_notice_minutes": 0, "max_days_ahead": 60, "timezone": "UTC",
        "weekly_availability": [
            {"weekday": d, "start": "09:00", "end": "17:00"} for d in range(7)
        ],
        "location_type": "custom", "location_detail": "https://meet.example.com/room",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_public_booking_lifecycle(api):
    h = await _register_owner(api)
    et_id = await _create_event_type(api, h)

    # Public event view (no auth).
    ev = await api.get(f"/api/public/scheduler/event/{et_id}")
    assert ev.status_code == 200
    assert ev.json()["name"] == "Intro Call"

    day = (utcnow().date() + timedelta(days=2)).isoformat()
    slots_resp = await api.get(f"/api/public/scheduler/event/{et_id}/slots?from={day}&to={day}")
    assert slots_resp.status_code == 200
    slots = slots_resp.json()["slots"]
    assert len(slots) == 16
    chosen = slots[0]

    # Book it.
    book = await api.post(f"/api/public/scheduler/event/{et_id}/book", json={
        "start_at": chosen, "invitee_name": "Ada", "invitee_email": "ada@example.com",
        "invitee_timezone": "America/Chicago", "invitee_notes": "Looking forward!",
    })
    assert book.status_code == 201, book.text
    token = book.json()["manage_token"]
    assert book.json()["status"] == "confirmed"

    # The slot is now gone.
    slots2 = (await api.get(f"/api/public/scheduler/event/{et_id}/slots?from={day}&to={day}")).json()["slots"]
    assert chosen not in slots2
    assert len(slots2) == 15

    # Double-booking the same slot is refused.
    dup = await api.post(f"/api/public/scheduler/event/{et_id}/book", json={
        "start_at": chosen, "invitee_name": "Bob", "invitee_email": "bob@example.com",
        "invitee_timezone": "UTC",
    })
    assert dup.status_code == 409

    # Manage via token → cancel → slot reopens.
    view = await api.get(f"/api/public/scheduler/booking/{token}")
    assert view.status_code == 200
    cancel = await api.post(f"/api/public/scheduler/booking/{token}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    slots3 = (await api.get(f"/api/public/scheduler/event/{et_id}/slots?from={day}&to={day}")).json()["slots"]
    assert chosen in slots3


@pytest.mark.asyncio
async def test_book_outside_availability_rejected(api):
    h = await _register_owner(api)
    et_id = await _create_event_type(api, h)
    # 03:00 UTC is outside the 09:00–17:00 window.
    bad_time = datetime.combine(utcnow().date() + timedelta(days=2), datetime.min.time()).replace(hour=3)
    r = await api.post(f"/api/public/scheduler/event/{et_id}/book", json={
        "start_at": bad_time.isoformat(), "invitee_name": "X", "invitee_email": "x@e.com",
        "invitee_timezone": "UTC",
    })
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_reschedule_moves_booking(api):
    h = await _register_owner(api)
    et_id = await _create_event_type(api, h)
    day = (utcnow().date() + timedelta(days=2)).isoformat()
    slots = (await api.get(f"/api/public/scheduler/event/{et_id}/slots?from={day}&to={day}")).json()["slots"]

    book = await api.post(f"/api/public/scheduler/event/{et_id}/book", json={
        "start_at": slots[0], "invitee_name": "Ada", "invitee_email": "ada@example.com",
        "invitee_timezone": "UTC",
    })
    token = book.json()["manage_token"]

    re = await api.post(f"/api/public/scheduler/booking/{token}/reschedule", json={"start_at": slots[5]})
    assert re.status_code == 200, re.text
    assert re.json()["start_at"].startswith(slots[5][:16])

    # The original slot is free again; the new slot is taken.
    slots2 = (await api.get(f"/api/public/scheduler/event/{et_id}/slots?from={day}&to={day}")).json()["slots"]
    assert slots[0] in slots2
    assert slots[5] not in slots2


@pytest.mark.asyncio
async def test_event_type_crud_requires_admin(api, make_user):
    from app.models.user import Role

    async def _login(email, password):
        r = await api.post("/api/auth/login", json={"email": email, "password": password})
        return {"X-CSRF-Token": r.json()["csrf_token"]}

    ed = await _login(**await make_user("ed@test.com", "EditorPass123", Role.editor))
    r = await api.post("/api/scheduler/event-types", headers=ed, json={
        "name": "X", "slug": "x", "weekly_availability": [], "timezone": "UTC",
    })
    assert r.status_code == 403

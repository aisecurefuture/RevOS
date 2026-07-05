"""Meeting scheduler — authenticated management (Phase 3).

Event-type CRUD is admin+ (it defines the business's availability); reading
event types and the booking list is any authenticated member.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.exceptions import RevOSError
from app.deps import DbSession, require_admin, require_authenticated, verify_csrf
from app.models.user import AdminUser
from app.schemas.scheduler import (
    BookingOut,
    EventTypeCreate,
    EventTypeOut,
    EventTypeUpdate,
)
from app.services import scheduler_service as svc

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


@router.get("/event-types", response_model=list[EventTypeOut])
async def list_event_types(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[EventTypeOut]:
    ets = await svc.list_event_types(db, _account_id(request))
    return [EventTypeOut.model_validate(e) for e in ets]


@router.post("/event-types", response_model=EventTypeOut, status_code=201)
async def create_event_type(
    body: EventTypeCreate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> EventTypeOut:
    data = body.model_dump()
    data["weekly_availability"] = [w.model_dump() for w in body.weekly_availability]
    et = await svc.create_event_type(db, _account_id(request), user, data)
    return EventTypeOut.model_validate(et)


@router.patch("/event-types/{event_type_id}", response_model=EventTypeOut)
async def update_event_type(
    event_type_id: uuid.UUID, body: EventTypeUpdate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> EventTypeOut:
    data = body.model_dump(exclude_unset=True)
    if "weekly_availability" in data and body.weekly_availability is not None:
        data["weekly_availability"] = [w.model_dump() for w in body.weekly_availability]
    et = await svc.update_event_type(db, event_type_id, _account_id(request), data)
    return EventTypeOut.model_validate(et)


@router.delete("/event-types/{event_type_id}", status_code=204)
async def delete_event_type(
    event_type_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> Response:
    await svc.delete_event_type(db, event_type_id, _account_id(request))
    return Response(status_code=204)


@router.get("/bookings", response_model=list[BookingOut])
async def list_bookings(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    upcoming_only: bool = Query(False),
) -> list[BookingOut]:
    bookings = await svc.list_bookings(db, _account_id(request), upcoming_only=upcoming_only)
    return [BookingOut.model_validate(b) for b in bookings]

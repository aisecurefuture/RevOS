"""Content items: CRUD, the approval state machine, ideas, calendars."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_admin, require_authenticated, require_editor, verify_csrf
from app.models.content import ContentChannel, ContentItem, ContentState
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.content import (
    CalendarCreate,
    CalendarOut,
    ContentItemCreate,
    ContentItemOut,
    ContentItemUpdate,
    IdeaRequest,
    IdeaResult,
    ScheduleRequest,
)
from app.services import content_service
from app.services.brand_service import get_brand_or_404
from app.services.crud import soft_delete

router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=list[ContentItemOut])
async def list_content(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    channel: ContentChannel | None = None,
    state: ContentState | None = None,
    calendar_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ContentItem]:
    return await content_service.list_content(
        db, brand_id=brand_id, channel=channel, state=state,
        calendar_id=calendar_id, limit=limit, offset=offset)


@router.post("", response_model=ContentItemOut, status_code=201)
async def create_content(
    body: ContentItemCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> ContentItem:
    item = await content_service.create_content(db, body.model_dump())
    await write_audit(db, action="content.create", user_id=user.id,
                      entity_type="content", entity_id=str(item.id), request=request)
    return item


@router.post("/ideas", response_model=IdeaResult)
async def generate_ideas(
    body: IdeaRequest,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> IdeaResult:
    brand = await get_brand_or_404(db, body.brand_id)
    ideas, source = await content_service.generate_ideas(
        db, brand=brand, channel=body.channel, count=body.count, topic=body.topic)
    return IdeaResult(ideas=ideas, source=source)


@router.get("/calendars", response_model=list[CalendarOut])
async def list_calendars(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
):
    return await content_service.list_calendars(db, brand_id)


@router.post("/calendars", response_model=CalendarOut, status_code=201)
async def create_calendar(
    body: CalendarCreate,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
):
    return await content_service.create_calendar(db, body.model_dump())


@router.get("/{content_id}", response_model=ContentItemOut)
async def get_content(
    content_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> ContentItem:
    return await content_service.get_content_or_404(db, content_id)


@router.patch("/{content_id}", response_model=ContentItemOut)
async def update_content(
    content_id: uuid.UUID,
    body: ContentItemUpdate,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> ContentItem:
    item = await content_service.get_content_or_404(db, content_id)
    return await content_service.update_content(db, item, body.model_dump(exclude_unset=True))


async def _transition(db, content_id, target, user, request, *, scheduled_at=None):
    item = await content_service.get_content_or_404(db, content_id)
    item = await content_service.transition(db, item, target, scheduled_at=scheduled_at)
    await write_audit(db, action=f"content.{target}", user_id=user.id,
                      entity_type="content", entity_id=str(content_id), request=request)
    return item


@router.post("/{content_id}/submit", response_model=ContentItemOut)
async def submit(content_id: uuid.UUID, request: Request, db: DbSession,
                 user: Annotated[AdminUser, Depends(require_editor)],
                 _: None = Depends(verify_csrf)) -> ContentItem:
    return await _transition(db, content_id, ContentState.needs_review, user, request)


@router.post("/{content_id}/approve", response_model=ContentItemOut)
async def approve(content_id: uuid.UUID, request: Request, db: DbSession,
                  user: Annotated[AdminUser, Depends(require_admin)],
                  _: None = Depends(verify_csrf)) -> ContentItem:
    # Approval is an admin action (aligns with rbac.can_approve); editors draft
    # and submit, admins approve and publish.
    return await _transition(db, content_id, ContentState.approved, user, request)


@router.post("/{content_id}/schedule", response_model=ContentItemOut)
async def schedule(content_id: uuid.UUID, body: ScheduleRequest, request: Request, db: DbSession,
                   user: Annotated[AdminUser, Depends(require_editor)],
                   _: None = Depends(verify_csrf)) -> ContentItem:
    return await _transition(db, content_id, ContentState.scheduled, user, request,
                             scheduled_at=body.scheduled_at)


@router.post("/{content_id}/publish", response_model=ContentItemOut)
async def publish(content_id: uuid.UUID, request: Request, db: DbSession,
                  user: Annotated[AdminUser, Depends(require_admin)],
                  _: None = Depends(verify_csrf)) -> ContentItem:
    # Publishing is an outbound action — admin only (approval-first).
    return await _transition(db, content_id, ContentState.published, user, request)


@router.post("/{content_id}/archive", response_model=ContentItemOut)
async def archive(content_id: uuid.UUID, request: Request, db: DbSession,
                  user: Annotated[AdminUser, Depends(require_editor)],
                  _: None = Depends(verify_csrf)) -> ContentItem:
    return await _transition(db, content_id, ContentState.archived, user, request)


@router.post("/{content_id}/repurpose", response_model=list[ContentItemOut])
async def repurpose(
    content_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    channels: Annotated[list[str], Body(embed=True)],
    _: None = Depends(verify_csrf),
) -> list[ContentItem]:
    item = await content_service.get_content_or_404(db, content_id)
    created = await content_service.repurpose(db, item, channels)
    await write_audit(db, action="content.repurpose", user_id=user.id,
                      entity_type="content", entity_id=str(content_id), request=request)
    return created


@router.delete("/{content_id}", response_model=Message)
async def delete_content(content_id: uuid.UUID, request: Request, db: DbSession,
                         user: Annotated[AdminUser, Depends(require_editor)],
                         _: None = Depends(verify_csrf)) -> Message:
    item = await content_service.get_content_or_404(db, content_id)
    await soft_delete(db, item)
    await write_audit(db, action="content.delete", user_id=user.id,
                      entity_type="content", entity_id=str(content_id), request=request)
    return Message(status="deleted")

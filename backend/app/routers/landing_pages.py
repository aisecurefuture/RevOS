"""Landing page CRUD (admin console). Reads require auth; writes require editor."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.campaign import LandingPage
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.landing import LandingCreate, LandingOut, LandingUpdate
from app.services import landing_service
from app.services.crud import soft_delete

router = APIRouter(prefix="/landing-pages", tags=["landing-pages"])


@router.get("", response_model=list[LandingOut])
async def list_pages(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[LandingPage]:
    return await landing_service.list_pages(db, brand_id=brand_id, limit=limit, offset=offset)


@router.post("", response_model=LandingOut, status_code=201)
async def create_page(
    body: LandingCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> LandingPage:
    page = await landing_service.create_page(db, body)
    await write_audit(db, action="landing.create", user_id=user.id,
                      entity_type="landing_page", entity_id=str(page.id), request=request)
    return page


@router.get("/{page_id}", response_model=LandingOut)
async def get_page(
    page_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> LandingPage:
    return await landing_service.get_page_or_404(db, page_id)


@router.patch("/{page_id}", response_model=LandingOut)
async def update_page(
    page_id: uuid.UUID,
    body: LandingUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> LandingPage:
    page = await landing_service.get_page_or_404(db, page_id)
    page = await landing_service.update_page(db, page, body)
    await write_audit(db, action="landing.update", user_id=user.id,
                      entity_type="landing_page", entity_id=str(page_id), request=request)
    return page


@router.delete("/{page_id}", response_model=Message)
async def delete_page(
    page_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    page = await landing_service.get_page_or_404(db, page_id)
    await soft_delete(db, page)
    await write_audit(db, action="landing.delete", user_id=user.id,
                      entity_type="landing_page", entity_id=str(page_id), request=request)
    return Message(status="deleted")

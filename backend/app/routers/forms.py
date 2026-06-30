"""Form CRUD (admin console). Reads require auth; writes require editor."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.campaign import Form
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.form import FormCreate, FormOut, FormUpdate
from app.services import form_service
from app.services.crud import soft_delete

router = APIRouter(prefix="/forms", tags=["forms"])


@router.get("", response_model=list[FormOut])
async def list_forms(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Form]:
    return await form_service.list_forms(db, brand_id=brand_id, limit=limit, offset=offset)


@router.post("", response_model=FormOut, status_code=201)
async def create_form(
    body: FormCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Form:
    form = await form_service.create_form(db, body)
    await write_audit(db, action="form.create", user_id=user.id,
                      entity_type="form", entity_id=str(form.id), request=request)
    return form


@router.get("/{form_id}", response_model=FormOut)
async def get_form(
    form_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Form:
    return await form_service.get_form_or_404(db, form_id)


@router.patch("/{form_id}", response_model=FormOut)
async def update_form(
    form_id: uuid.UUID,
    body: FormUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Form:
    form = await form_service.get_form_or_404(db, form_id)
    form = await form_service.update_form(db, form, body)
    await write_audit(db, action="form.update", user_id=user.id,
                      entity_type="form", entity_id=str(form_id), request=request)
    return form


@router.delete("/{form_id}", response_model=Message)
async def delete_form(
    form_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    form = await form_service.get_form_or_404(db, form_id)
    await soft_delete(db, form)
    await write_audit(db, action="form.delete", user_id=user.id,
                      entity_type="form", entity_id=str(form_id), request=request)
    return Message(status="deleted")

"""Email template CRUD. Reads require auth; writes require editor."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.email import EmailTemplate
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.email import TemplateCreate, TemplateOut, TemplateUpdate
from app.services import template_service
from app.services.crud import soft_delete

router = APIRouter(prefix="/email-templates", tags=["email-templates"])


@router.get("", response_model=list[TemplateOut])
async def list_templates(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[EmailTemplate]:
    return await template_service.list_templates(db, brand_id=brand_id, limit=limit, offset=offset)


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> EmailTemplate:
    template = await template_service.create_template(db, body.model_dump())
    await write_audit(db, action="template.create", user_id=user.id,
                      entity_type="email_template", entity_id=str(template.id), request=request)
    return template


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> EmailTemplate:
    return await template_service.get_template_or_404(db, template_id)


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> EmailTemplate:
    template = await template_service.get_template_or_404(db, template_id)
    template = await template_service.update_template(db, template, body.model_dump(exclude_unset=True))
    await write_audit(db, action="template.update", user_id=user.id,
                      entity_type="email_template", entity_id=str(template_id), request=request)
    return template


@router.delete("/{template_id}", response_model=Message)
async def delete_template(
    template_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    template = await template_service.get_template_or_404(db, template_id)
    await soft_delete(db, template)
    await write_audit(db, action="template.delete", user_id=user.id,
                      entity_type="email_template", entity_id=str(template_id), request=request)
    return Message(status="deleted")

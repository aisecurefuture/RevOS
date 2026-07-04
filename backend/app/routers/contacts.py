"""Contacts CRUD + CSV/LinkedIn import + export."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.crm import Contact
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.crm import (
    ContactCreate,
    ContactImportResult,
    ContactOut,
    ContactUpdate,
)
from app.services import crm_service, linkedin_import
from app.services.crud import get_active, soft_delete

router = APIRouter(prefix="/contacts", tags=["contacts"])

_MAX_IMPORT_BYTES = 25 * 1024 * 1024  # 25 MB cap


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Contact]:
    return await crm_service.list_contacts(
        db, brand_id=brand_id, source=source, search=search, limit=limit, offset=offset)


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(
    body: ContactCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Contact:
    data = body.model_dump()
    if data.get("email"):
        data["email"] = str(data["email"]).lower()
    contact = await crm_service.create_contact(db, data)
    await write_audit(db, action="contact.create", user_id=user.id,
                      entity_type="contact", entity_id=str(contact.id), request=request)
    return contact


@router.get("/export", response_class=PlainTextResponse)
async def export_contacts(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    source: str | None = None,
) -> PlainTextResponse:
    contacts = await crm_service.list_contacts(db, brand_id=brand_id, source=source, limit=200)
    return PlainTextResponse(
        crm_service.contacts_to_csv(contacts), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/import", response_model=ContactImportResult)
async def import_contacts(
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    file: Annotated[UploadFile, File()],
    brand_id: Annotated[uuid.UUID | None, Form()] = None,
    _: None = Depends(verify_csrf),
) -> ContactImportResult:
    raw = await file.read()
    if len(raw) > _MAX_IMPORT_BYTES:
        raise RevOSError("File too large.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RevOSError("File must be UTF-8 CSV.") from exc

    rows = linkedin_import.parse_contacts_csv(content)
    result = await linkedin_import.import_contacts(db, brand_id=brand_id, rows=rows)
    await write_audit(db, action="contact.import", user_id=user.id, request=request,
                      meta={k: v for k, v in result.items() if k != "note"})
    return ContactImportResult(**result)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(
    contact_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Contact:
    return await get_active(db, Contact, contact_id)


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Contact:
    contact = await get_active(db, Contact, contact_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("email"):
        data["email"] = str(data["email"]).lower()
    for key, value in data.items():
        setattr(contact, key, value)
    contact.lead_score = crm_service.score_contact(
        email=contact.email, title=contact.title,
        has_company=contact.company_id is not None, linkedin=contact.linkedin_url)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    await write_audit(db, action="contact.update", user_id=user.id,
                      entity_type="contact", entity_id=str(contact_id), request=request)
    return contact


@router.delete("/{contact_id}", response_model=Message)
async def delete_contact(
    contact_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    contact = await get_active(db, Contact, contact_id)
    await soft_delete(db, contact)
    await write_audit(db, action="contact.delete", user_id=user.id,
                      entity_type="contact", entity_id=str(contact_id), request=request)
    return Message(status="deleted")

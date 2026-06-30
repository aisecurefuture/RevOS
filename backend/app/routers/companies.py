"""Companies CRUD."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.text import clean_text
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.crm import Company
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.crm import CompanyCreate, CompanyOut, CompanyUpdate
from app.services.crud import get_active, list_active, soft_delete

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyOut])
async def list_companies(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Company]:
    filters = [Company.brand_id == brand_id] if brand_id else []
    return await list_active(db, Company, filters=filters, limit=limit, offset=offset)


@router.post("", response_model=CompanyOut, status_code=201)
async def create_company(
    body: CompanyCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Company:
    data = body.model_dump()
    data["name"] = clean_text(data["name"]) or data["name"]
    data["notes"] = clean_text(data.get("notes"))
    company = Company(**data)
    db.add(company)
    await db.flush()
    await db.refresh(company)
    await write_audit(db, action="company.create", user_id=user.id,
                      entity_type="company", entity_id=str(company.id), request=request)
    return company


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Company:
    return await get_active(db, Company, company_id)


@router.patch("/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Company:
    company = await get_active(db, Company, company_id)
    data = body.model_dump(exclude_unset=True)
    for field in ("name", "notes"):
        if field in data and data[field] is not None:
            data[field] = clean_text(data[field])
    for key, value in data.items():
        setattr(company, key, value)
    db.add(company)
    await db.flush()
    await db.refresh(company)
    await write_audit(db, action="company.update", user_id=user.id,
                      entity_type="company", entity_id=str(company_id), request=request)
    return company


@router.delete("/{company_id}", response_model=Message)
async def delete_company(
    company_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    company = await get_active(db, Company, company_id)
    await soft_delete(db, company)
    await write_audit(db, action="company.delete", user_id=user.id,
                      entity_type="company", entity_id=str(company_id), request=request)
    return Message(status="deleted")

"""Leads (admin console): list, filter, detail, tag, CSV export, delete."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.lead import ConsentStatus, Lead
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.lead import LeadDetailOut, LeadOut, TagApply
from app.services import lead_service
from app.services.crud import get_active, soft_delete

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=list[LeadOut])
async def list_leads(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    consent_status: ConsentStatus | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Lead]:
    return await lead_service.list_leads(
        db, brand_id=brand_id, consent_status=consent_status, source=source,
        search=search, limit=limit, offset=offset,
    )


@router.get("/export", response_class=PlainTextResponse)
async def export_leads(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    consent_status: ConsentStatus | None = None,
    source: str | None = None,
) -> PlainTextResponse:
    leads = await lead_service.list_leads(
        db, brand_id=brand_id, consent_status=consent_status, source=source, limit=200, offset=0,
    )
    csv_text = lead_service.leads_to_csv(leads)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )


@router.get("/{lead_id}", response_model=LeadDetailOut)
async def get_lead(
    lead_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> LeadDetailOut:
    lead = await get_active(db, Lead, lead_id)
    detail = LeadDetailOut.model_validate(lead)
    detail.tags = [t.name for t in await lead_service.list_lead_tags(db, lead_id)]
    return detail


@router.post("/{lead_id}/tags", response_model=LeadDetailOut)
async def tag_lead(
    lead_id: uuid.UUID,
    body: TagApply,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> LeadDetailOut:
    lead = await get_active(db, Lead, lead_id)
    await lead_service.apply_tags(db, lead, body.tags, lead.brand_id)
    await write_audit(db, action="lead.tag", user_id=user.id,
                      entity_type="lead", entity_id=str(lead_id), request=request)
    detail = LeadDetailOut.model_validate(lead)
    detail.tags = [t.name for t in await lead_service.list_lead_tags(db, lead_id)]
    return detail


@router.delete("/{lead_id}", response_model=Message)
async def delete_lead(
    lead_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    lead = await get_active(db, Lead, lead_id)
    await soft_delete(db, lead)
    await write_audit(db, action="lead.delete", user_id=user.id,
                      entity_type="lead", entity_id=str(lead_id), request=request)
    return Message(status="deleted")

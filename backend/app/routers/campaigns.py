"""Campaign CRUD. Reads require auth; writes require editor."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.campaign import Campaign
from app.models.user import AdminUser
from app.schemas.campaign import CampaignCreate, CampaignOut, CampaignUpdate
from app.schemas.common import Message
from app.services import campaign_service
from app.services.crud import soft_delete

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Campaign]:
    return await campaign_service.list_campaigns(db, brand_id=brand_id, limit=limit, offset=offset)


@router.post("", response_model=CampaignOut, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Campaign:
    campaign = await campaign_service.create_campaign(db, body)
    await write_audit(db, action="campaign.create", user_id=user.id,
                      entity_type="campaign", entity_id=str(campaign.id), request=request)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Campaign:
    return await campaign_service.get_campaign_or_404(db, campaign_id)


@router.patch("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Campaign:
    campaign = await campaign_service.get_campaign_or_404(db, campaign_id)
    campaign = await campaign_service.update_campaign(db, campaign, body)
    await write_audit(db, action="campaign.update", user_id=user.id,
                      entity_type="campaign", entity_id=str(campaign_id), request=request)
    return campaign


@router.delete("/{campaign_id}", response_model=Message)
async def delete_campaign(
    campaign_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    campaign = await campaign_service.get_campaign_or_404(db, campaign_id)
    await soft_delete(db, campaign)
    await write_audit(db, action="campaign.delete", user_id=user.id,
                      entity_type="campaign", entity_id=str(campaign_id), request=request)
    return Message(status="deleted")

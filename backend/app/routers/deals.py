"""Deals CRUD + pipeline stages."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.text import clean_text
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.crm import Deal, DealStatus, PipelineStage
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.crm import DealCreate, DealMove, DealOut, DealUpdate, PipelineStageOut
from app.services import crm_service, revenue_service
from app.services.crud import get_active, list_active, soft_delete

router = APIRouter(prefix="/deals", tags=["deals"])


# --- Pipeline stages --------------------------------------------------------
@router.get("/pipeline", response_model=list[PipelineStageOut])
async def get_pipeline(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
) -> list[PipelineStage]:
    stages = await crm_service.list_pipeline(db, brand_id)
    if not stages:
        stages = await crm_service.ensure_default_pipeline(db, brand_id)
    return stages


# --- Deals ------------------------------------------------------------------
@router.get("", response_model=list[DealOut])
async def list_deals(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    pipeline_stage_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Deal]:
    filters: list = []
    if brand_id:
        filters.append(Deal.brand_id == brand_id)
    if pipeline_stage_id:
        filters.append(Deal.pipeline_stage_id == pipeline_stage_id)
    return await list_active(db, Deal, filters=filters, limit=limit, offset=offset)


@router.post("", response_model=DealOut, status_code=201)
async def create_deal(
    body: DealCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Deal:
    data = body.model_dump()
    data["name"] = clean_text(data["name"]) or data["name"]
    deal = await crm_service.create_deal(db, data)
    await write_audit(db, action="deal.create", user_id=user.id,
                      entity_type="deal", entity_id=str(deal.id), request=request)
    return deal


@router.get("/{deal_id}", response_model=DealOut)
async def get_deal(
    deal_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Deal:
    return await get_active(db, Deal, deal_id)


@router.patch("/{deal_id}", response_model=DealOut)
async def update_deal(
    deal_id: uuid.UUID,
    body: DealUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Deal:
    deal = await get_active(db, Deal, deal_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(deal, key, value)
    db.add(deal)
    await db.flush()
    await db.refresh(deal)
    await write_audit(db, action="deal.update", user_id=user.id,
                      entity_type="deal", entity_id=str(deal_id), request=request)
    return deal


@router.post("/{deal_id}/move", response_model=DealOut)
async def move_deal(
    deal_id: uuid.UUID,
    body: DealMove,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Deal:
    deal = await get_active(db, Deal, deal_id)
    stage = await get_active(db, PipelineStage, body.pipeline_stage_id)
    deal.pipeline_stage_id = stage.id
    if stage.is_won:
        deal.status = DealStatus.won
    elif stage.is_lost:
        deal.status = DealStatus.lost
    else:
        deal.status = DealStatus.open
    db.add(deal)
    await db.flush()
    # Won deals record revenue (idempotent per deal) for the analytics layer.
    if deal.status == DealStatus.won:
        await revenue_service.record_from_deal(db, deal)
    await db.refresh(deal)
    await write_audit(db, action="deal.move", user_id=user.id,
                      entity_type="deal", entity_id=str(deal_id), request=request,
                      meta={"stage": stage.slug})
    return deal


@router.delete("/{deal_id}", response_model=Message)
async def delete_deal(
    deal_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    deal = await get_active(db, Deal, deal_id)
    await soft_delete(db, deal)
    await write_audit(db, action="deal.delete", user_id=user.id,
                      entity_type="deal", entity_id=str(deal_id), request=request)
    return Message(status="deleted")

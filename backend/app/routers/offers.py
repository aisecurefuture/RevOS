"""Offer CRUD. Reads require auth; writes require editor."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.offer import Offer
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.offer import OfferCreate, OfferOut, OfferUpdate
from app.services import offer_service
from app.services.crud import soft_delete

router = APIRouter(prefix="/offers", tags=["offers"])


@router.get("", response_model=list[OfferOut])
async def list_offers(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Offer]:
    return await offer_service.list_offers(db, brand_id=brand_id, limit=limit, offset=offset)


@router.post("", response_model=OfferOut, status_code=201)
async def create_offer(
    body: OfferCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Offer:
    offer = await offer_service.create_offer(db, body)
    await write_audit(db, action="offer.create", user_id=user.id,
                      entity_type="offer", entity_id=str(offer.id), request=request)
    return offer


@router.get("/{offer_id}", response_model=OfferOut)
async def get_offer(
    offer_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Offer:
    return await offer_service.get_offer_or_404(db, offer_id)


@router.patch("/{offer_id}", response_model=OfferOut)
async def update_offer(
    offer_id: uuid.UUID,
    body: OfferUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Offer:
    offer = await offer_service.get_offer_or_404(db, offer_id)
    offer = await offer_service.update_offer(db, offer, body)
    await write_audit(db, action="offer.update", user_id=user.id,
                      entity_type="offer", entity_id=str(offer_id), request=request)
    return offer


@router.delete("/{offer_id}", response_model=Message)
async def delete_offer(
    offer_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    offer = await offer_service.get_offer_or_404(db, offer_id)
    await soft_delete(db, offer)
    await write_audit(db, action="offer.delete", user_id=user.id,
                      entity_type="offer", entity_id=str(offer_id), request=request)
    return Message(status="deleted")

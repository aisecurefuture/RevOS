"""AI Matching Engine API — creators, products, and ranked matches (Phase 3, M3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.core.tenancy import get_active_account
from app.deps import (
    DbSession,
    require_authenticated,
    require_editor,
    require_platform_admin,
    verify_csrf,
)
from app.models.matching import CollaborationDirection, CollaborationRequest, Creator, MatchProduct
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.matching import (
    BrokerCollaborationCreate,
    CollaborationRequestCreate,
    CollaborationRequestOut,
    CollaborationRespond,
    CreatorCreate,
    CreatorDiscoveryOut,
    CreatorMatchOut,
    CreatorOut,
    CreatorUpdate,
    MatchProductCreate,
    MatchProductOut,
    MatchProductUpdate,
    ProductDiscoveryOut,
    ProductMatchOut,
)
from app.services import collaboration_service, creator_service
from app.services.crud import get_active, soft_delete

router = APIRouter(prefix="/matching", tags=["matching"])


def _account_id() -> uuid.UUID:
    acct = get_active_account()
    if acct is None:
        raise RevOSError("No active account.", code="no_account", status_code=403)
    return acct


# --- Creators ---------------------------------------------------------------
@router.get("/creators", response_model=list[CreatorOut])
async def list_creators(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    industry: str | None = None,
    size_tier: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Creator]:
    return await creator_service.list_creators(
        db, industry=industry, size_tier=size_tier, status=status,
        search=search, limit=limit, offset=offset)


@router.post("/creators", response_model=CreatorOut, status_code=201)
async def create_creator(
    body: CreatorCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Creator:
    creator = await creator_service.create_creator(db, body.model_dump())
    await write_audit(db, action="creator.create", user_id=user.id,
                      entity_type="creator", entity_id=str(creator.id), request=request)
    return creator


@router.get("/creators/{creator_id}", response_model=CreatorOut)
async def get_creator(
    creator_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Creator:
    return await get_active(db, Creator, creator_id)


@router.patch("/creators/{creator_id}", response_model=CreatorOut)
async def update_creator(
    creator_id: uuid.UUID,
    body: CreatorUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Creator:
    creator = await get_active(db, Creator, creator_id)
    creator = await creator_service.update_creator(db, creator, body.model_dump(exclude_unset=True))
    await write_audit(db, action="creator.update", user_id=user.id,
                      entity_type="creator", entity_id=str(creator_id), request=request)
    return creator


@router.delete("/creators/{creator_id}", response_model=Message)
async def delete_creator(
    creator_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    creator = await get_active(db, Creator, creator_id)
    await soft_delete(db, creator)
    await write_audit(db, action="creator.delete", user_id=user.id,
                      entity_type="creator", entity_id=str(creator_id), request=request)
    return Message(status="deleted")


@router.get("/creators/{creator_id}/matches", response_model=list[ProductMatchOut])
async def creator_matches(
    creator_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    creator = await get_active(db, Creator, creator_id)
    return await creator_service.matches_for_creator(db, creator, limit=limit)


# --- Products ---------------------------------------------------------------
@router.get("/products", response_model=list[MatchProductOut])
async def list_products(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[MatchProduct]:
    return await creator_service.list_products(
        db, status=status, search=search, limit=limit, offset=offset)


@router.post("/products", response_model=MatchProductOut, status_code=201)
async def create_product(
    body: MatchProductCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> MatchProduct:
    product = await creator_service.create_product(db, body.model_dump())
    await write_audit(db, action="match_product.create", user_id=user.id,
                      entity_type="match_product", entity_id=str(product.id), request=request)
    return product


@router.get("/products/{product_id}", response_model=MatchProductOut)
async def get_product(
    product_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> MatchProduct:
    return await get_active(db, MatchProduct, product_id)


@router.patch("/products/{product_id}", response_model=MatchProductOut)
async def update_product(
    product_id: uuid.UUID,
    body: MatchProductUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> MatchProduct:
    product = await get_active(db, MatchProduct, product_id)
    product = await creator_service.update_product(db, product, body.model_dump(exclude_unset=True))
    await write_audit(db, action="match_product.update", user_id=user.id,
                      entity_type="match_product", entity_id=str(product_id), request=request)
    return product


@router.delete("/products/{product_id}", response_model=Message)
async def delete_product(
    product_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    product = await get_active(db, MatchProduct, product_id)
    await soft_delete(db, product)
    await write_audit(db, action="match_product.delete", user_id=user.id,
                      entity_type="match_product", entity_id=str(product_id), request=request)
    return Message(status="deleted")


@router.get("/products/{product_id}/matches", response_model=list[CreatorMatchOut])
async def product_matches(
    product_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    product = await get_active(db, MatchProduct, product_id)
    return await creator_service.matches_for_product(db, product, limit=limit)


# --- Marketplace discovery (cross-tenant, consent-gated) --------------------
@router.get("/discover/creators", response_model=list[CreatorDiscoveryOut])
async def discover_creators(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    industry: str | None = None,
    size_tier: str | None = None,
    search: str | None = None,
    rank_product_id: uuid.UUID | None = None,   # rank against one of YOUR products
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    rank_product = await get_active(db, MatchProduct, rank_product_id) if rank_product_id else None
    return await creator_service.search_discoverable_creators(
        db, industry=industry, size_tier=size_tier, search=search,
        rank_product=rank_product, limit=limit)


@router.get("/discover/products", response_model=list[ProductDiscoveryOut])
async def discover_products(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    industry: str | None = None,
    search: str | None = None,
    rank_creator_id: uuid.UUID | None = None,   # rank against one of YOUR creators
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    rank_creator = await get_active(db, Creator, rank_creator_id) if rank_creator_id else None
    return await creator_service.search_discoverable_products(
        db, industry=industry, search=search, rank_creator=rank_creator, limit=limit)


# --- Collaboration requests -------------------------------------------------
async def _load_request_as_party(db: DbSession, request_id: uuid.UUID) -> CollaborationRequest:
    req = await db.get(CollaborationRequest, request_id)
    if req is None or req.deleted_at is not None:
        raise RevOSError("Request not found.", code="not_found", status_code=404)
    acct = _account_id()
    if acct not in (req.initiator_account_id, req.recipient_account_id):
        raise RevOSError("You are not a party to this request.", code="forbidden", status_code=403)
    return req


@router.post("/collaborations", response_model=CollaborationRequestOut, status_code=201)
async def create_collaboration(
    body: CollaborationRequestCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationRequest:
    req = await collaboration_service.create_request(
        db, initiator_account_id=_account_id(), initiator_user_id=user.id,
        direction=body.direction, creator_id=body.creator_id, product_id=body.product_id,
        message=body.message)
    await write_audit(db, action="collaboration.create", user_id=user.id,
                      entity_type="collaboration_request", entity_id=str(req.id), request=request)
    return req


@router.get("/collaborations", response_model=list[CollaborationRequestOut])
async def list_collaborations(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    box: str = Query("incoming", pattern="^(incoming|outgoing)$"),
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CollaborationRequest]:
    return await collaboration_service.list_for_account(
        db, _account_id(), box=box, status=status, limit=limit, offset=offset)


@router.get("/collaborations/{request_id}", response_model=CollaborationRequestOut)
async def get_collaboration(
    request_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> CollaborationRequest:
    return await _load_request_as_party(db, request_id)


@router.post("/collaborations/{request_id}/respond", response_model=CollaborationRequestOut)
async def respond_collaboration(
    request_id: uuid.UUID,
    body: CollaborationRespond,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationRequest:
    req = await db.get(CollaborationRequest, request_id)
    if req is None or req.deleted_at is not None:
        raise RevOSError("Request not found.", code="not_found", status_code=404)
    if req.recipient_account_id != _account_id():
        raise RevOSError("Only the recipient can respond to this request.",
                         code="forbidden", status_code=403)
    req = await collaboration_service.respond(db, req, accept=body.accept, note=body.note,
                                              channel="in_app")
    await write_audit(db, action=f"collaboration.{req.status}", user_id=user.id,
                      entity_type="collaboration_request", entity_id=str(req.id), request=request)
    return req


@router.post("/collaborations/{request_id}/withdraw", response_model=CollaborationRequestOut)
async def withdraw_collaboration(
    request_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationRequest:
    req = await db.get(CollaborationRequest, request_id)
    if req is None or req.deleted_at is not None:
        raise RevOSError("Request not found.", code="not_found", status_code=404)
    req = await collaboration_service.withdraw(db, req, actor_account_id=_account_id())
    await write_audit(db, action="collaboration.withdrawn", user_id=user.id,
                      entity_type="collaboration_request", entity_id=str(req.id), request=request)
    return req


# --- Platform-admin brokering ----------------------------------------------
@router.get("/broker/creators", response_model=list[CreatorDiscoveryOut])
async def broker_search_creators(
    db: DbSession,
    _admin: Annotated[AdminUser, Depends(require_platform_admin)],
    industry: str | None = None,
    size_tier: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    # Admin sees the whole market — discoverable or not.
    return await creator_service.search_discoverable_creators(
        db, industry=industry, size_tier=size_tier, search=search,
        include_hidden=True, limit=limit)


@router.post("/broker/collaborations", response_model=CollaborationRequestOut, status_code=201)
async def broker_collaboration(
    body: BrokerCollaborationCreate,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_platform_admin)],
    _: None = Depends(verify_csrf),
) -> CollaborationRequest:
    req = await collaboration_service.create_request(
        db, initiator_account_id=body.initiator_account_id, initiator_user_id=admin.id,
        direction=body.direction, creator_id=body.creator_id, product_id=body.product_id,
        message=body.message, brokered_by_user_id=admin.id)
    await write_audit(db, action="collaboration.brokered", user_id=admin.id,
                      entity_type="collaboration_request", entity_id=str(req.id), request=request)
    return req

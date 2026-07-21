"""AI Matching Engine API — creators, products, and ranked matches (Phase 3, M3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.matching import Creator, MatchProduct
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.matching import (
    CreatorCreate,
    CreatorMatchOut,
    CreatorOut,
    CreatorUpdate,
    MatchProductCreate,
    MatchProductOut,
    MatchProductUpdate,
    ProductMatchOut,
)
from app.services import creator_service
from app.services.crud import get_active, soft_delete

router = APIRouter(prefix="/matching", tags=["matching"])


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

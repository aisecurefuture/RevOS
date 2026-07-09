"""Brand Book — the grounding source of truth (Phase 3 M1).

Editing the book / claims / facts is editor+ (it's content configuration);
reading is any authenticated member. Everything is scoped to a brand that the
service confirms belongs to the active account.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.brand import Brand
from app.models.user import AdminUser
from app.schemas.brand_book import (
    BrandBookOut,
    BrandBookUpdate,
    CheckOut,
    CheckRequest,
    ClaimCreate,
    ClaimOut,
    FactCreate,
    FactOut,
    GroundingOut,
)
from app.services import brand_book_service as svc

router = APIRouter(prefix="/brand-book", tags=["brand-book"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


async def _brand_in_account(db: DbSession, brand_id: uuid.UUID, account_id: uuid.UUID) -> Brand:
    brand = await db.get(Brand, brand_id)
    if brand is None or brand.account_id != account_id or brand.deleted_at is not None:
        raise NotFoundError("Brand not found.")
    return brand


@router.get("/{brand_id}", response_model=BrandBookOut)
async def get_book(
    brand_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> BrandBookOut:
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    book = await svc.get_or_create_book(db, brand_id, account_id)
    return BrandBookOut.model_validate(book)


@router.patch("/{brand_id}", response_model=BrandBookOut)
async def update_book(
    brand_id: uuid.UUID, body: BrandBookUpdate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> BrandBookOut:
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    book = await svc.update_book(db, brand_id, account_id, body.model_dump(exclude_unset=True))
    return BrandBookOut.model_validate(book)


# --- Claims -----------------------------------------------------------------

@router.get("/{brand_id}/claims", response_model=list[ClaimOut])
async def list_claims(
    brand_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[ClaimOut]:
    await _brand_in_account(db, brand_id, _account_id(request))
    return [ClaimOut.model_validate(c) for c in await svc.list_claims(db, brand_id)]


@router.post("/{brand_id}/claims", response_model=ClaimOut, status_code=201)
async def create_claim(
    brand_id: uuid.UUID, body: ClaimCreate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> ClaimOut:
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    claim = await svc.create_claim(db, brand_id, account_id, user, body.model_dump())
    return ClaimOut.model_validate(claim)


@router.delete("/{brand_id}/claims/{claim_id}", status_code=204)
async def delete_claim(
    brand_id: uuid.UUID, claim_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> Response:
    await _brand_in_account(db, brand_id, _account_id(request))
    await svc.delete_claim(db, claim_id, brand_id)
    return Response(status_code=204)


# --- Facts ------------------------------------------------------------------

@router.get("/{brand_id}/facts", response_model=list[FactOut])
async def list_facts(
    brand_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[FactOut]:
    await _brand_in_account(db, brand_id, _account_id(request))
    return [FactOut.model_validate(f) for f in await svc.list_facts(db, brand_id)]


@router.post("/{brand_id}/facts", response_model=FactOut, status_code=201)
async def create_fact(
    brand_id: uuid.UUID, body: FactCreate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> FactOut:
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    fact = await svc.create_fact(db, brand_id, account_id, user, body.model_dump())
    return FactOut.model_validate(fact)


@router.delete("/{brand_id}/facts/{fact_id}", status_code=204)
async def delete_fact(
    brand_id: uuid.UUID, fact_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> Response:
    await _brand_in_account(db, brand_id, _account_id(request))
    await svc.delete_fact(db, fact_id, brand_id)
    return Response(status_code=204)


# --- Grounding + content check ---------------------------------------------

@router.get("/{brand_id}/grounding", response_model=GroundingOut)
async def grounding(
    brand_id: uuid.UUID, request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> GroundingOut:
    """Preview the assembled source-of-truth context that will ground generation."""
    await _brand_in_account(db, brand_id, _account_id(request))
    pack = await svc.assemble_grounding_context(db, brand_id)
    return GroundingOut(
        prompt_context=pack.prompt_context,
        approved_claims=pack.approved_claims,
        banned_terms=pack.banned_terms,
        required_disclaimers=pack.required_disclaimers,
        is_published=pack.is_published,
    )


@router.post("/{brand_id}/check", response_model=CheckOut)
async def check(
    brand_id: uuid.UUID, body: CheckRequest, request: Request, db: DbSession,
    user: AdminUser = Depends(require_editor), _: None = Depends(verify_csrf),
) -> CheckOut:
    """Run the same combined gate real generation goes through — deterministic
    (banned terms, missing disclaimers, ungrounded numeric claims) plus the
    optional LLM claim-verification layer — so this preview tool can't pass
    something that would actually get flagged/blocked in production."""
    await _brand_in_account(db, brand_id, _account_id(request))
    result = await svc.verify_content(db, brand_id, body.text, require_disclaimers=body.require_disclaimers)
    return CheckOut(**result.to_dict())

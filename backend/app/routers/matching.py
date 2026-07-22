"""AI Matching Engine API — creators, products, and ranked matches (Phase 3, M3)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.config import settings
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
from app.models.base import utcnow
from app.models.matching import CollaborationDirection, CollaborationRequest, Creator, MatchProduct
from app.models.offer import Offer
from app.models.reputation import Review
from app.schemas.collaboration import OfferImportCreate
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.matching import (
    BrokerCollaborationCreate,
    CollaborationRequestCreate,
    CollaborationRequestOut,
    CollaborationRespond,
    CreatorClaimInviteOut,
    CreatorClaimRequest,
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
    PublicPageSettingsOut,
    PublicPageSettingsUpdate,
)
from app.schemas.reputation import (
    InsightsOut,
    ReputationScoreOut,
    ReviewCreate,
    ReviewOut,
    ReviewRespond,
)
from app.services import (
    collaboration_service,
    creator_service,
    insights_service,
    public_profile_service,
    reputation_service,
    review_service,
)
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


@router.get("/creators/claimed/mine", response_model=list[CreatorOut])
async def list_my_claimed_creators(
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[Creator]:
    """Creator-portal groundwork: profiles this user has verified themselves
    against — the anchor for a future creator-facing dashboard."""
    return await creator_service.list_claimed_by(db, user.id)


@router.post("/creators/claim", response_model=CreatorOut)
async def claim_creator(
    body: CreatorClaimRequest,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
    _: None = Depends(verify_csrf),
) -> Creator:
    creator = await creator_service.claim_creator(db, body.token, user_id=user.id)
    await write_audit(db, action="creator.claim", user_id=user.id,
                      entity_type="creator", entity_id=str(creator.id), request=request)
    return creator


async def _load_own_creator(db: DbSession, creator_id: uuid.UUID, user: AdminUser) -> Creator:
    """A creator record is 'yours' either by tenant ownership OR because you're
    the person who claimed it (Phase 6 portal groundwork) — either grants
    access to your own profile/insights, distinct from the public,
    discoverable-gated view used by ``_reputation_visible``."""
    creator = await db.get(Creator, creator_id)
    if creator is None or creator.deleted_at is not None:
        raise RevOSError("Creator not found.", code="not_found", status_code=404)
    account_id = get_active_account()
    owns = account_id is not None and creator.account_id == account_id
    claimed_by_me = creator.claimed_by_user_id == user.id
    if not (owns or claimed_by_me):
        raise RevOSError("Creator not found.", code="not_found", status_code=404)
    return creator


@router.get("/creators/{creator_id}", response_model=CreatorOut)
async def get_creator(
    creator_id: uuid.UUID,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Creator:
    return await _load_own_creator(db, creator_id, user)


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


@router.post("/creators/{creator_id}/claim-invite", response_model=CreatorClaimInviteOut)
async def create_claim_invite(
    creator_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> dict:
    """Only the account that manages this Creator record may invite them to
    claim it — get_active enforces that (tenant-scoped: 404s otherwise)."""
    creator = await get_active(db, Creator, creator_id)
    invite = creator_service.make_claim_invite(creator.id)
    await write_audit(db, action="creator.claim_invite", user_id=user.id,
                      entity_type="creator", entity_id=str(creator_id), request=request)
    return invite


def _public_settings_out(creator: Creator) -> dict:
    return {
        "enabled": creator.public_page_enabled,
        "slug": creator.public_slug,
        "fields": creator.public_fields or [],
        "share_url": f"{settings.public_base_url}/c/{creator.public_slug}" if creator.public_slug else None,
        "view_count": creator.public_view_count,
    }


@router.get("/creators/{creator_id}/public-page", response_model=PublicPageSettingsOut)
async def get_public_page_settings(
    creator_id: uuid.UUID,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
) -> dict:
    creator = await _load_own_creator(db, creator_id, user)
    return _public_settings_out(creator)


@router.patch("/creators/{creator_id}/public-page", response_model=PublicPageSettingsOut)
async def update_public_page_settings(
    creator_id: uuid.UUID,
    body: PublicPageSettingsUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> dict:
    creator = await _load_own_creator(db, creator_id, user)
    creator = await public_profile_service.update_public_page(
        db, creator, enabled=body.enabled, slug=body.slug, fields=body.fields)
    await write_audit(db, action="creator.public_page_update", user_id=user.id,
                      entity_type="creator", entity_id=str(creator_id), request=request)
    return _public_settings_out(creator)


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


async def _reputation_visible(subject, user_id: uuid.UUID | None = None) -> bool:
    """A subject's reputation is visible if it's discoverable, it's yours by
    tenant ownership, or you're the person who claimed it."""
    return (bool(getattr(subject, "discoverable", False))
            or subject.account_id == get_active_account()
            or (user_id is not None and getattr(subject, "claimed_by_user_id", None) == user_id))


@router.get("/creators/{creator_id}/reputation", response_model=ReputationScoreOut)
async def creator_reputation(
    creator_id: uuid.UUID,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
) -> dict:
    creator = await db.get(Creator, creator_id)
    if creator is None or creator.deleted_at is not None:
        raise RevOSError("Creator not found.", code="not_found", status_code=404)
    if not await _reputation_visible(creator, user.id):
        raise RevOSError("This creator's reputation is not visible.", code="forbidden", status_code=403)
    score = await reputation_service.reputation_for(
        db, subject_type="creator", subject_id=creator.id,
        account_id=creator.account_id, now=utcnow())
    return score.as_dict()


@router.get("/products/{product_id}/reputation", response_model=ReputationScoreOut)
async def product_reputation(
    product_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> dict:
    product = await db.get(MatchProduct, product_id)
    if product is None or product.deleted_at is not None:
        raise RevOSError("Product not found.", code="not_found", status_code=404)
    if not await _reputation_visible(product):
        raise RevOSError("This product's reputation is not visible.", code="forbidden", status_code=403)
    score = await reputation_service.reputation_for(
        db, subject_type="match_product", subject_id=product.id,
        account_id=product.account_id, now=utcnow())
    return score.as_dict()


@router.get("/creators/{creator_id}/insights", response_model=InsightsOut)
async def get_creator_insights(
    creator_id: uuid.UUID,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
) -> dict:
    # Own dashboard only — by tenant ownership OR having claimed the profile.
    creator = await _load_own_creator(db, creator_id, user)
    return await insights_service.creator_insights(db, creator, now=utcnow())


@router.get("/products/{product_id}/insights", response_model=InsightsOut)
async def get_product_insights(
    product_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> dict:
    product = await get_active(db, MatchProduct, product_id)
    return await insights_service.product_insights(db, product, now=utcnow())


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


@router.post("/products/import-offer", response_model=MatchProductOut, status_code=201)
async def import_product_from_offer(
    body: OfferImportCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> MatchProduct:
    """Seed a marketplace product from one of your existing offers — reuse the
    homework (name/description/brand) and link offer_id, then add marketplace
    fields."""
    offer = await get_active(db, Offer, body.offer_id)   # tenant-scoped: your own offer only
    overrides = body.model_dump(exclude={"offer_id"})
    product = await creator_service.product_from_offer(db, offer, overrides)
    await write_audit(db, action="match_product.import_offer", user_id=user.id,
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


@router.get("/collaborations/pending-reviews", response_model=list[CollaborationRequestOut])
async def pending_review_prompts(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[CollaborationRequest]:
    """Accepted collaborations you were a party to but haven't reviewed yet —
    the "leave a review" prompt surface. Registered ABOVE /{request_id} so the
    literal "pending-reviews" segment isn't swallowed as a UUID path param."""
    return await review_service.pending_review_prompts(db, _account_id())


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


# --- Reviews (RK3 — feedback workflow) --------------------------------------
@router.post("/collaborations/{request_id}/reviews", response_model=ReviewOut, status_code=201)
async def submit_review(
    request_id: uuid.UUID,
    body: ReviewCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Review:
    if body.collaboration_request_id != request_id:
        raise RevOSError("collaboration_request_id must match the URL.",
                         code="mismatched_collaboration", status_code=400)
    collab = await _load_request_as_party(db, request_id)
    review = await review_service.submit_review(
        db, collab, reviewer_account_id=_account_id(), reviewer_user_id=user.id,
        rating=body.rating, dimension_ratings=body.dimension_ratings, comment=body.comment)
    await write_audit(db, action="review.submit", user_id=user.id,
                      entity_type="review", entity_id=str(review.id), request=request)
    return review


@router.get("/collaborations/{request_id}/reviews", response_model=list[ReviewOut])
async def list_collaboration_reviews(
    request_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[Review]:
    await _load_request_as_party(db, request_id)   # 403s / 404s for non-parties
    return await review_service.list_for_collaboration(db, request_id)


@router.post("/reviews/{review_id}/respond", response_model=ReviewOut)
async def respond_to_review(
    review_id: uuid.UUID,
    body: ReviewRespond,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Review:
    review = await db.get(Review, review_id)
    if review is None or review.deleted_at is not None:
        raise RevOSError("Review not found.", code="not_found", status_code=404)
    review = await review_service.respond_to_review(
        db, review, actor_account_id=_account_id(), response=body.response)
    await write_audit(db, action="review.respond", user_id=user.id,
                      entity_type="review", entity_id=str(review.id), request=request)
    return review


@router.get("/creators/{creator_id}/reviews", response_model=list[ReviewOut])
async def creator_reviews(
    creator_id: uuid.UUID,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_authenticated)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Review]:
    creator = await db.get(Creator, creator_id)
    if creator is None or creator.deleted_at is not None:
        raise RevOSError("Creator not found.", code="not_found", status_code=404)
    if not await _reputation_visible(creator, user.id):
        raise RevOSError("This creator's reviews are not visible.", code="forbidden", status_code=403)
    return await review_service.list_for_subject(
        db, subject_type="creator", subject_id=creator_id, limit=limit, offset=offset)


@router.get("/products/{product_id}/reviews", response_model=list[ReviewOut])
async def product_reviews(
    product_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Review]:
    product = await db.get(MatchProduct, product_id)
    if product is None or product.deleted_at is not None:
        raise RevOSError("Product not found.", code="not_found", status_code=404)
    if not await _reputation_visible(product):
        raise RevOSError("This product's reviews are not visible.", code="forbidden", status_code=403)
    return await review_service.list_for_subject(
        db, subject_type="match_product", subject_id=product_id, limit=limit, offset=offset)


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

"""Creator & MatchProduct persistence + match orchestration (Phase 3, M3).

DB-touching layer over the pure ``matching_service`` engine: CRUD for creators
and products, deriving the rating-cohort fields (size_tier, primary industry) on
write, and running ranked matches.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.exceptions import RevOSError
from app.core.security import make_signed_token, read_signed_token
from app.models.base import utcnow
from app.models.matching import Creator, CreatorStatus, MatchProduct, MatchProductStatus
from app.services import matching_service
from app.services.crud import list_active
from app.services.industry_taxonomy import size_tier_for

_CLAIM_SALT = "creator-claim"
_CLAIM_MAX_AGE_DAYS = 14

_MATCH_POOL_CAP = 500   # creators/products scored per match request


def _derive_cohort_fields(data: dict) -> dict:
    """size_tier from follower_count; backfill the primary industry scalar from
    the highest-weight entry in the affinity list."""
    if "follower_count" in data:
        data["size_tier"] = size_tier_for(data.get("follower_count"))
    inds = data.get("industries")
    if inds:
        dicts = [i if isinstance(i, dict) else i.model_dump() for i in inds]
        data["industries"] = dicts
        if not data.get("industry"):
            primary = max(dicts, key=lambda d: d.get("weight", 0) or 0)
            data["industry"] = primary.get("industry")
    return data


# --- Creators ---------------------------------------------------------------
async def create_creator(db: AsyncSession, data: dict) -> Creator:
    data = _derive_cohort_fields(dict(data))
    if data.get("discoverable"):
        data["discoverable_at"] = utcnow()
    creator = Creator(**data)
    db.add(creator)
    await db.flush()
    await db.refresh(creator)
    return creator


async def update_creator(db: AsyncSession, creator: Creator, data: dict) -> Creator:
    data = _derive_cohort_fields(dict(data))
    # Stamp the opt-in moment the first time a creator becomes discoverable.
    if data.get("discoverable") and not creator.discoverable:
        creator.discoverable_at = utcnow()
    for key, value in data.items():
        setattr(creator, key, value)
    db.add(creator)
    await db.flush()
    await db.refresh(creator)
    return creator


async def list_creators(
    db: AsyncSession, *, industry: str | None = None, size_tier: str | None = None,
    status: str | None = None, search: str | None = None, limit: int = 50, offset: int = 0,
) -> list[Creator]:
    filters: list = []
    if industry:
        filters.append(Creator.industry == industry)
    if size_tier:
        filters.append(Creator.size_tier == size_tier)
    if status:
        filters.append(Creator.status == status)
    if search:
        like = f"%{search.lower()}%"
        filters.append((Creator.display_name.ilike(like)) | (Creator.handle.ilike(like)))
    return await list_active(db, Creator, filters=filters,
                             order_by=Creator.follower_count.desc(), limit=limit, offset=offset)


# --- Products ---------------------------------------------------------------
async def create_product(db: AsyncSession, data: dict) -> MatchProduct:
    data = _derive_cohort_fields(dict(data))
    if data.get("discoverable"):
        data["discoverable_at"] = utcnow()
    product = MatchProduct(**data)
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def product_from_offer(db: AsyncSession, offer, overrides: dict) -> MatchProduct:
    """Seed a marketplace product from an existing Offer — reuse the homework:
    name/description/brand come from the offer, and offer_id links them. The
    caller layers marketplace-specific fields (industry, target audience,
    discoverability) on top via ``overrides``."""
    data = {
        "name": offer.name, "description": offer.description,
        "brand_id": offer.brand_id, "offer_id": offer.id,
    }
    data.update({k: v for k, v in overrides.items() if v is not None})
    return await create_product(db, data)


async def update_product(db: AsyncSession, product: MatchProduct, data: dict) -> MatchProduct:
    data = _derive_cohort_fields(dict(data))
    if data.get("discoverable") and not product.discoverable:
        product.discoverable_at = utcnow()
    for key, value in data.items():
        setattr(product, key, value)
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def list_products(
    db: AsyncSession, *, status: str | None = None, search: str | None = None,
    limit: int = 50, offset: int = 0,
) -> list[MatchProduct]:
    filters: list = []
    if status:
        filters.append(MatchProduct.status == status)
    if search:
        filters.append(MatchProduct.name.ilike(f"%{search.lower()}%"))
    return await list_active(db, MatchProduct, filters=filters, limit=limit, offset=offset)


# --- Cross-tenant marketplace discovery -------------------------------------
# These deliberately BYPASS tenant scoping (no scope_stmt / account filter) —
# the one carve-out in the app. It is gated entirely by the `discoverable`
# opt-in flag: only creators/products that opted into the marketplace are
# visible across tenants. Results carry the public match profile, never raw
# contact details (those are revealed only after a request is accepted).
async def search_discoverable_creators(
    db: AsyncSession, *, industry: str | None = None, size_tier: str | None = None,
    search: str | None = None, rank_product: MatchProduct | None = None,
    include_hidden: bool = False, limit: int = 50,
) -> list[dict]:
    stmt = select(Creator).where(
        Creator.deleted_at.is_(None), Creator.status == CreatorStatus.active,
    )
    if not include_hidden:                       # include_hidden = platform-admin broker view
        stmt = stmt.where(Creator.discoverable == True)  # noqa: E712
    if industry:
        stmt = stmt.where(Creator.industry == industry)
    if size_tier:
        stmt = stmt.where(Creator.size_tier == size_tier)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where((Creator.display_name.ilike(like)) | (Creator.handle.ilike(like)))
    stmt = stmt.order_by(Creator.follower_count.desc()).limit(_MATCH_POOL_CAP)
    creators = list((await db.execute(stmt)).scalars().all())
    if rank_product is not None:
        ranked = matching_service.rank_creators(rank_product, creators)
        return [{"creator": c, "score": s.as_dict()} for c, s in ranked[:limit]]
    return [{"creator": c, "score": None} for c in creators[:limit]]


async def search_discoverable_products(
    db: AsyncSession, *, industry: str | None = None, search: str | None = None,
    rank_creator: Creator | None = None, include_hidden: bool = False, limit: int = 50,
) -> list[dict]:
    stmt = select(MatchProduct).where(
        MatchProduct.deleted_at.is_(None), MatchProduct.status == MatchProductStatus.active,
    )
    if not include_hidden:
        stmt = stmt.where(MatchProduct.discoverable == True)  # noqa: E712
    if industry:
        stmt = stmt.where(MatchProduct.industry == industry)
    if search:
        stmt = stmt.where(MatchProduct.name.ilike(f"%{search.lower()}%"))
    stmt = stmt.limit(_MATCH_POOL_CAP)
    products = list((await db.execute(stmt)).scalars().all())
    if rank_creator is not None:
        ranked = matching_service.rank_products(rank_creator, products)
        return [{"product": p, "score": s.as_dict()} for p, s in ranked[:limit]]
    return [{"product": p, "score": None} for p in products[:limit]]


# --- Matching ---------------------------------------------------------------
async def matches_for_product(
    db: AsyncSession, product: MatchProduct, *, weights: dict | None = None, limit: int = 50,
) -> list[dict]:
    creators = await list_active(
        db, Creator, filters=[Creator.status == CreatorStatus.active],
        order_by=Creator.follower_count.desc(), limit=_MATCH_POOL_CAP,
    )
    ranked = matching_service.rank_creators(product, creators, weights)
    return [{"creator": c, "score": s.as_dict()} for c, s in ranked[:limit]]


async def matches_for_creator(
    db: AsyncSession, creator: Creator, *, weights: dict | None = None, limit: int = 50,
) -> list[dict]:
    products = await list_active(
        db, MatchProduct, filters=[MatchProduct.status == MatchProductStatus.active],
        limit=_MATCH_POOL_CAP,
    )
    ranked = matching_service.rank_products(creator, products, weights)
    return [{"product": p, "score": s.as_dict()} for p, s in ranked[:limit]]


# --- Creator-portal groundwork: claim a managed Creator record --------------
def make_claim_invite(creator_id: uuid.UUID) -> dict:
    """Only the account that owns/manages the Creator record may generate this
    (enforced by the router via tenant-scoped get_active before calling)."""
    token = make_signed_token({"creator_id": str(creator_id)}, salt=_CLAIM_SALT)
    return {
        "token": token,
        "claim_url": f"{settings.public_base_url}/claim-creator?token={token}",
        "expires_in_days": _CLAIM_MAX_AGE_DAYS,
    }


async def claim_creator(db: AsyncSession, token: str, *, user_id: uuid.UUID) -> Creator:
    data = read_signed_token(token, salt=_CLAIM_SALT,
                             max_age_seconds=_CLAIM_MAX_AGE_DAYS * 24 * 60 * 60)
    creator = await db.get(Creator, uuid.UUID(data["creator_id"]))
    if creator is None or creator.deleted_at is not None:
        raise RevOSError("This creator profile no longer exists.", code="not_found", status_code=404)
    if creator.claimed_by_user_id is not None:
        if creator.claimed_by_user_id == user_id:
            return creator   # idempotent — already claimed by you
        raise RevOSError("This profile has already been claimed by someone else.",
                         code="already_claimed", status_code=409)

    creator.claimed_by_user_id = user_id
    creator.claimed_at = utcnow()
    db.add(creator)
    await db.flush()
    await db.refresh(creator)
    return creator


async def list_claimed_by(db: AsyncSession, user_id: uuid.UUID) -> list[Creator]:
    stmt = select(Creator).where(
        Creator.claimed_by_user_id == user_id, Creator.deleted_at.is_(None),
    ).order_by(Creator.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())

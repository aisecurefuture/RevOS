"""Creator & MatchProduct persistence + match orchestration (Phase 3, M3).

DB-touching layer over the pure ``matching_service`` engine: CRUD for creators
and products, deriving the rating-cohort fields (size_tier, primary industry) on
write, and running ranked matches.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.matching import Creator, CreatorStatus, MatchProduct, MatchProductStatus
from app.services import matching_service
from app.services.crud import list_active
from app.services.industry_taxonomy import size_tier_for

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
    creator = Creator(**_derive_cohort_fields(dict(data)))
    db.add(creator)
    await db.flush()
    await db.refresh(creator)
    return creator


async def update_creator(db: AsyncSession, creator: Creator, data: dict) -> Creator:
    data = _derive_cohort_fields(dict(data))
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
    product = MatchProduct(**_derive_cohort_fields(dict(data)))
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return product


async def update_product(db: AsyncSession, product: MatchProduct, data: dict) -> MatchProduct:
    data = _derive_cohort_fields(dict(data))
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

"""Offer service logic."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import clean_text, slugify
from app.models.offer import Offer
from app.schemas.offer import OfferCreate, OfferUpdate
from app.services.crud import get_active, list_active, unique_slug


async def list_offers(
    db: AsyncSession,
    *,
    brand_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Offer]:
    filters = [Offer.brand_id == brand_id] if brand_id else []
    return await list_active(db, Offer, filters=filters, limit=limit, offset=offset)


async def get_offer_or_404(db: AsyncSession, offer_id: uuid.UUID) -> Offer:
    return await get_active(db, Offer, offer_id)


async def create_offer(db: AsyncSession, body: OfferCreate) -> Offer:
    base = slugify(body.slug or body.name)
    slug = await unique_slug(db, Offer, base, brand_id=body.brand_id)
    offer = Offer(
        brand_id=body.brand_id,
        offer_type=body.offer_type,
        name=clean_text(body.name) or body.name,
        slug=slug,
        subtitle=clean_text(body.subtitle),
        description=clean_text(body.description),
        status=body.status,
        price_cents=body.price_cents,
        currency=body.currency.upper(),
        stripe_price_id=body.stripe_price_id,
        stripe_payment_link=body.stripe_payment_link,
        external_url=body.external_url,
        asset_url=body.asset_url,
        details=body.details,
    )
    db.add(offer)
    await db.flush()
    await db.refresh(offer)
    return offer


async def update_offer(db: AsyncSession, offer: Offer, body: OfferUpdate) -> Offer:
    data = body.model_dump(exclude_unset=True)
    for field in ("name", "subtitle", "description"):
        if field in data and data[field] is not None:
            data[field] = clean_text(data[field])
    if "currency" in data and data["currency"]:
        data["currency"] = data["currency"].upper()
    for key, value in data.items():
        setattr(offer, key, value)
    db.add(offer)
    await db.flush()
    await db.refresh(offer)
    return offer

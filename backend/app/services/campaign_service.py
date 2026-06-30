"""Campaign service logic."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import clean_text, slugify
from app.models.campaign import Campaign
from app.schemas.campaign import CampaignCreate, CampaignUpdate
from app.services.crud import get_active, list_active, unique_slug


async def list_campaigns(
    db: AsyncSession,
    *,
    brand_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Campaign]:
    filters = [Campaign.brand_id == brand_id] if brand_id else []
    return await list_active(db, Campaign, filters=filters, limit=limit, offset=offset)


async def get_campaign_or_404(db: AsyncSession, campaign_id: uuid.UUID) -> Campaign:
    return await get_active(db, Campaign, campaign_id)


async def create_campaign(db: AsyncSession, body: CampaignCreate) -> Campaign:
    base = slugify(body.slug or body.name)
    slug = await unique_slug(db, Campaign, base, brand_id=body.brand_id)
    campaign = Campaign(
        brand_id=body.brand_id,
        name=clean_text(body.name) or body.name,
        slug=slug,
        objective=clean_text(body.objective),
        status=body.status,
        channel=body.channel,
        theme=clean_text(body.theme),
        utm_campaign=body.utm_campaign,
        budget_cents=body.budget_cents,
        offer_id=body.offer_id,
        start_at=body.start_at,
        end_at=body.end_at,
        settings=body.settings,
    )
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


async def update_campaign(
    db: AsyncSession, campaign: Campaign, body: CampaignUpdate
) -> Campaign:
    data = body.model_dump(exclude_unset=True)
    for field in ("name", "objective", "theme"):
        if field in data and data[field] is not None:
            data[field] = clean_text(data[field])
    for key, value in data.items():
        setattr(campaign, key, value)
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign

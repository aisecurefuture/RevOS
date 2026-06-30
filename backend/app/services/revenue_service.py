"""Revenue recording (manual + from won deals; Stripe-ready)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.analytics import RevenueRecord, RevenueStatus
from app.models.base import utcnow
from app.models.crm import Deal
from app.services.crud import list_active


async def record_revenue(db: AsyncSession, data: dict) -> RevenueRecord:
    data.setdefault("occurred_at", utcnow())
    record = RevenueRecord(**data)
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def record_from_deal(db: AsyncSession, deal: Deal) -> RevenueRecord | None:
    """Create a revenue record when a deal is won (idempotent per deal)."""
    if not deal.amount_cents:
        return None
    existing = await db.execute(
        select(RevenueRecord).where(RevenueRecord.deal_id == deal.id)
    )
    if existing.scalar_one_or_none() is not None:
        return None
    return await record_revenue(db, {
        "brand_id": deal.brand_id, "offer_id": deal.offer_id, "deal_id": deal.id,
        "contact_id": deal.contact_id, "amount_cents": deal.amount_cents,
        "currency": deal.currency, "source": "deal", "status": RevenueStatus.paid,
        "occurred_at": utcnow(),
    })


async def list_revenue(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, limit: int = 100, offset: int = 0
) -> list[RevenueRecord]:
    filters = [RevenueRecord.brand_id == brand_id] if brand_id else []
    return await list_active(db, RevenueRecord, filters=filters, limit=limit, offset=offset)

"""Analytics & revenue intelligence aggregations.

Metrics are derived directly from the domain tables (leads, email messages,
deals, revenue records, UTM captures) so they are always accurate — no separate
rollup to keep in sync. The Event table backs page-view / custom tracking.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import RevenueRecord, RevenueStatus
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.crm import Deal, DealStatus, PipelineStage
from app.models.email import EmailMessage, EmailStatus
from app.models.lead import ConsentStatus, Lead, UTMCapture
from app.models.offer import Offer
from app.models.user import AuditLog

_SENT_STATUSES = (EmailStatus.sent, EmailStatus.delivered, EmailStatus.opened, EmailStatus.clicked)


def _brand_filter(column, brand_id):
    return [column == brand_id] if brand_id else []


async def leads_by_source(db: AsyncSession, brand_id: uuid.UUID | None) -> list[dict]:
    stmt = select(
        func.coalesce(Lead.source, "direct").label("source"), func.count().label("count")
    ).where(Lead.deleted_at.is_(None), *_brand_filter(Lead.brand_id, brand_id)).group_by(
        Lead.source
    ).order_by(func.count().desc())
    rows = (await db.execute(stmt)).all()
    return [{"source": r.source, "count": r.count} for r in rows]


async def leads_by_brand(db: AsyncSession) -> list[dict]:
    stmt = select(
        Brand.name, func.count(Lead.id).label("count")
    ).join(Lead, Lead.brand_id == Brand.id).where(Lead.deleted_at.is_(None)).group_by(
        Brand.name
    ).order_by(func.count(Lead.id).desc())
    return [{"brand": r.name, "count": r.count} for r in (await db.execute(stmt)).all()]


async def email_stats(db: AsyncSession, brand_id: uuid.UUID | None) -> dict:
    base = [EmailMessage.deleted_at.is_(None), *_brand_filter(EmailMessage.brand_id, brand_id)]
    sent = (await db.execute(select(func.count()).where(
        *base, EmailMessage.status.in_(_SENT_STATUSES)))).scalar_one()
    opened = (await db.execute(select(func.count()).where(
        *base, EmailMessage.open_count > 0))).scalar_one()
    clicked = (await db.execute(select(func.count()).where(
        *base, EmailMessage.click_count > 0))).scalar_one()
    return {
        "sent": sent, "opened": opened, "clicked": clicked,
        "open_rate": round(opened / sent, 4) if sent else 0.0,
        "click_rate": round(clicked / sent, 4) if sent else 0.0,
    }


async def revenue_by_offer(db: AsyncSession, brand_id: uuid.UUID | None) -> list[dict]:
    stmt = select(
        func.coalesce(Offer.name, "Unattributed").label("offer"),
        func.sum(RevenueRecord.amount_cents).label("cents"),
    ).select_from(RevenueRecord).join(
        Offer, Offer.id == RevenueRecord.offer_id, isouter=True
    ).where(
        RevenueRecord.status == RevenueStatus.paid,
        *_brand_filter(RevenueRecord.brand_id, brand_id),
    ).group_by(Offer.name).order_by(func.sum(RevenueRecord.amount_cents).desc())
    return [{"offer": r.offer, "amount_cents": int(r.cents or 0)}
            for r in (await db.execute(stmt)).all()]


async def pipeline_value(db: AsyncSession, brand_id: uuid.UUID | None) -> list[dict]:
    stmt = select(
        PipelineStage.name, PipelineStage.order_index,
        func.count(Deal.id).label("count"),
        func.coalesce(func.sum(Deal.amount_cents), 0).label("cents"),
    ).select_from(PipelineStage).join(
        Deal, (Deal.pipeline_stage_id == PipelineStage.id) & (Deal.deleted_at.is_(None))
        & (Deal.status == DealStatus.open), isouter=True,
    ).where(
        PipelineStage.deleted_at.is_(None), *_brand_filter(PipelineStage.brand_id, brand_id)
    ).group_by(
        PipelineStage.name, PipelineStage.order_index
    ).order_by(PipelineStage.order_index)
    return [{"stage": r.name, "count": r.count, "amount_cents": int(r.cents)}
            for r in (await db.execute(stmt)).all()]


async def funnel(db: AsyncSession, brand_id: uuid.UUID | None) -> list[dict]:
    lead_base = [Lead.deleted_at.is_(None), *_brand_filter(Lead.brand_id, brand_id)]
    total_leads = (await db.execute(select(func.count()).where(*lead_base))).scalar_one()
    confirmed = (await db.execute(select(func.count()).where(
        *lead_base, Lead.consent_status == ConsentStatus.confirmed))).scalar_one()
    deal_base = [Deal.deleted_at.is_(None), *_brand_filter(Deal.brand_id, brand_id)]
    open_deals = (await db.execute(select(func.count()).where(
        *deal_base, Deal.status == DealStatus.open))).scalar_one()
    won = (await db.execute(select(func.count()).where(
        *deal_base, Deal.status == DealStatus.won))).scalar_one()
    return [
        {"stage": "Leads", "count": total_leads},
        {"stage": "Confirmed", "count": confirmed},
        {"stage": "Open deals", "count": open_deals},
        {"stage": "Won", "count": won},
    ]


async def utm_performance(db: AsyncSession, brand_id: uuid.UUID | None) -> list[dict]:
    stmt = select(
        func.coalesce(UTMCapture.utm_source, "direct").label("source"),
        func.coalesce(UTMCapture.utm_campaign, "—").label("campaign"),
        func.count().label("count"),
    ).where(*_brand_filter(UTMCapture.brand_id, brand_id)).group_by(
        UTMCapture.utm_source, UTMCapture.utm_campaign
    ).order_by(func.count().desc()).limit(50)
    return [{"source": r.source, "campaign": r.campaign, "count": r.count}
            for r in (await db.execute(stmt)).all()]


async def overview(db: AsyncSession, brand_id: uuid.UUID | None) -> dict:
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    rev_mtd = (await db.execute(select(func.coalesce(func.sum(RevenueRecord.amount_cents), 0)).where(
        RevenueRecord.status == RevenueStatus.paid,
        RevenueRecord.occurred_at >= month_start,
        *_brand_filter(RevenueRecord.brand_id, brand_id),
    ))).scalar_one()

    new_leads = (await db.execute(select(func.count()).where(
        Lead.deleted_at.is_(None), Lead.created_at >= now - timedelta(days=30),
        *_brand_filter(Lead.brand_id, brand_id),
    ))).scalar_one()

    subscribers = (await db.execute(select(func.count()).where(
        Lead.deleted_at.is_(None), Lead.consent_status == ConsentStatus.confirmed,
        *_brand_filter(Lead.brand_id, brand_id),
    ))).scalar_one()

    pipeline = await pipeline_value(db, brand_id)
    pipeline_total = sum(s["amount_cents"] for s in pipeline)

    pending_approvals = (await db.execute(select(func.count()).where(
        ApprovalRequest.status == ApprovalStatus.pending,
        *_brand_filter(ApprovalRequest.brand_id, brand_id),
    ))).scalar_one()

    activity = (await db.execute(select(AuditLog).order_by(
        AuditLog.created_at.desc()).limit(10))).scalars().all()

    return {
        "revenue_mtd_cents": int(rev_mtd),
        "new_leads_30d": new_leads,
        "subscribers": subscribers,
        "pipeline_value_cents": pipeline_total,
        "pending_approvals": pending_approvals,
        "leads_by_source": await leads_by_source(db, brand_id),
        "email": await email_stats(db, brand_id),
        "funnel": await funnel(db, brand_id),
        "recent_activity": [
            {"action": a.action, "entity_type": a.entity_type,
             "at": a.created_at.isoformat()} for a in activity
        ],
    }

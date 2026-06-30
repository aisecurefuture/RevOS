"""Analytics dashboards, revenue recording, and UTM link management."""

from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from app.core.audit import write_audit
from app.deps import DbSession, require_admin, require_authenticated, require_editor, verify_csrf
from app.models.user import AdminUser
from app.schemas.analytics import (
    RevenueCreate,
    RevenueOut,
    UTMLinkCreate,
    UTMLinkOut,
)
from app.services import analytics_service, revenue_service, utm_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

CurrentUser = Annotated[AdminUser, Depends(require_authenticated)]


@router.get("/overview")
async def overview(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None) -> dict:
    return await analytics_service.overview(db, brand_id)


@router.get("/leads-by-source")
async def leads_by_source(db: DbSession, _user: CurrentUser,
                          brand_id: uuid.UUID | None = None) -> list[dict]:
    return await analytics_service.leads_by_source(db, brand_id)


@router.get("/leads-by-brand")
async def leads_by_brand(db: DbSession, _user: CurrentUser) -> list[dict]:
    return await analytics_service.leads_by_brand(db)


@router.get("/email")
async def email(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None) -> dict:
    return await analytics_service.email_stats(db, brand_id)


@router.get("/revenue")
async def revenue(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None) -> list[dict]:
    return await analytics_service.revenue_by_offer(db, brand_id)


@router.get("/pipeline")
async def pipeline(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None) -> list[dict]:
    from app.services import crm_service
    await crm_service.ensure_default_pipeline(db, brand_id)  # idempotent
    return await analytics_service.pipeline_value(db, brand_id)


@router.get("/funnel")
async def funnel(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None) -> list[dict]:
    return await analytics_service.funnel(db, brand_id)


@router.get("/utm")
async def utm(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None) -> list[dict]:
    return await analytics_service.utm_performance(db, brand_id)


@router.get("/export", response_class=PlainTextResponse)
async def export(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None
                 ) -> PlainTextResponse:
    rows = await analytics_service.leads_by_source(db, brand_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["source", "leads"])
    for r in rows:
        writer.writerow([r["source"], r["count"]])
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=analytics.csv"})


# --- Revenue ----------------------------------------------------------------
@router.post("/revenue", response_model=RevenueOut, status_code=201)
async def record_revenue(
    body: RevenueCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
):
    record = await revenue_service.record_revenue(db, body.model_dump())
    await write_audit(db, action="revenue.record", user_id=user.id,
                      entity_type="revenue", entity_id=str(record.id), request=request)
    return record


@router.get("/revenue/records", response_model=list[RevenueOut])
async def list_revenue(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None):
    return await revenue_service.list_revenue(db, brand_id=brand_id)


# --- UTM links --------------------------------------------------------------
@router.post("/utm-links", response_model=UTMLinkOut, status_code=201)
async def create_utm_link(
    body: UTMLinkCreate,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
):
    return await utm_service.create_link(db, {**body.model_dump(), "created_by_user_id": user.id})


@router.get("/utm-links", response_model=list[UTMLinkOut])
async def list_utm_links(db: DbSession, _user: CurrentUser, brand_id: uuid.UUID | None = None):
    return await utm_service.list_links(db, brand_id)

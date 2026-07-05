"""Content autopilot — per-brand config + on-demand run (Phase 3).

Admin+ only: enabling auto_publish lets the system post to connected accounts
without a human, so it's a high-privilege setting (the Brand Book gate is the
safety net, but the switch is still admin-gated).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import NotFoundError, RevOSError
from app.deps import DbSession, require_admin, verify_csrf
from app.models.brand import Brand
from app.models.user import AdminUser
from app.schemas.autopilot import AutopilotConfigOut, AutopilotConfigUpdate, AutopilotRunOut
from app.services import content_autopilot_service as svc

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


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


@router.get("/{brand_id}", response_model=AutopilotConfigOut)
async def get_config(
    brand_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin),
) -> AutopilotConfigOut:
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    cfg = await svc.get_or_create_config(db, brand_id, account_id)
    return AutopilotConfigOut.model_validate(cfg)


@router.patch("/{brand_id}", response_model=AutopilotConfigOut)
async def update_config(
    brand_id: uuid.UUID, body: AutopilotConfigUpdate, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> AutopilotConfigOut:
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    cfg = await svc.update_config(db, brand_id, account_id, user, body.model_dump(exclude_unset=True))
    return AutopilotConfigOut.model_validate(cfg)


@router.post("/{brand_id}/run", response_model=AutopilotRunOut)
async def run_now(
    brand_id: uuid.UUID, request: Request, db: DbSession,
    user: AdminUser = Depends(require_admin), _: None = Depends(verify_csrf),
) -> AutopilotRunOut:
    """Generate a batch right now (ignores the cadence). Useful for testing the
    grounded generation + accuracy gate before turning on hands-off publishing."""
    account_id = _account_id(request)
    await _brand_in_account(db, brand_id, account_id)
    stats = await svc.run_now(db, brand_id, account_id)
    return AutopilotRunOut(**stats)

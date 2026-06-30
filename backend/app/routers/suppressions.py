"""Suppression list management (admin only — contains opt-out PII)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_admin, verify_csrf
from app.models.email import Suppression
from app.models.user import AdminUser
from app.schemas.common import Message
from app.schemas.email import SuppressionCreate, SuppressionOut
from app.services.crud import get_active, list_active, soft_delete

router = APIRouter(prefix="/suppressions", tags=["suppressions"])


@router.get("", response_model=list[SuppressionOut])
async def list_suppressions(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_admin)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Suppression]:
    filters = [Suppression.brand_id == brand_id] if brand_id else []
    return await list_active(db, Suppression, filters=filters, limit=limit, offset=offset)


@router.post("", response_model=SuppressionOut, status_code=201)
async def add_suppression(
    body: SuppressionCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> Suppression:
    suppression = Suppression(
        brand_id=body.brand_id, email=str(body.email).lower().strip(),
        reason=body.reason, note=body.note, source="manual",
    )
    db.add(suppression)
    await db.flush()
    await db.refresh(suppression)
    await write_audit(db, action="suppression.add", user_id=user.id,
                      entity_type="suppression", entity_id=str(suppression.id), request=request)
    return suppression


@router.delete("/{suppression_id}", response_model=Message)
async def remove_suppression(
    suppression_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> Message:
    suppression = await get_active(db, Suppression, suppression_id)
    await soft_delete(db, suppression)
    await write_audit(db, action="suppression.remove", user_id=user.id,
                      entity_type="suppression", entity_id=str(suppression_id), request=request)
    return Message(status="removed")

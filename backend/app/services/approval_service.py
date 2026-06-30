"""Generic approval-request lifecycle — the human-in-the-loop gate.

Any sensitive action (bulk send, sequence activation, publish, AI apply) creates
an ApprovalRequest. A human with sufficient role approves or rejects; the caller
executes the side effect only after approval.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.base import utcnow
from app.services.crud import get_active, list_active


async def create_approval(
    db: AsyncSession,
    *,
    action_type: ApprovalAction,
    title: str,
    brand_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    summary: str | None = None,
    risk_notes: str | None = None,
    payload: dict | None = None,
    requested_by: uuid.UUID | None = None,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        action_type=action_type, title=title, brand_id=brand_id,
        entity_type=entity_type, entity_id=entity_id, summary=summary,
        risk_notes=risk_notes, payload=payload or {}, requested_by_user_id=requested_by,
    )
    db.add(approval)
    await db.flush()
    await db.refresh(approval)
    return approval


async def list_pending(
    db: AsyncSession, *, brand_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0
) -> list[ApprovalRequest]:
    filters = [ApprovalRequest.status == ApprovalStatus.pending]
    if brand_id:
        filters.append(ApprovalRequest.brand_id == brand_id)
    return await list_active(db, ApprovalRequest, filters=filters, limit=limit, offset=offset)


async def get_or_404(db: AsyncSession, approval_id: uuid.UUID) -> ApprovalRequest:
    return await get_active(db, ApprovalRequest, approval_id)


async def mark_approved(
    db: AsyncSession, approval: ApprovalRequest, *, user_id: uuid.UUID
) -> ApprovalRequest:
    approval.status = ApprovalStatus.approved
    approval.reviewed_by_user_id = user_id
    approval.reviewed_at = utcnow()
    db.add(approval)
    await db.flush()
    return approval


async def mark_rejected(
    db: AsyncSession, approval: ApprovalRequest, *, user_id: uuid.UUID, reason: str | None
) -> ApprovalRequest:
    approval.status = ApprovalStatus.rejected
    approval.reviewed_by_user_id = user_id
    approval.reviewed_at = utcnow()
    approval.decision_reason = reason
    db.add(approval)
    await db.flush()
    return approval

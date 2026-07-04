"""Approval queue: list, view, approve, reject.

Approving executes the gated side effect based on the request's action type
(e.g. campaign_send dispatches the prepared messages). Approve/reject require
admin; viewing requires any authenticated user.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_admin, require_authenticated, verify_csrf
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.user import AdminUser
from app.schemas.approval import ApprovalDecision, ApprovalOut, ApprovalResult
from app.services import approval_service, campaign_email_service, sequence_engine

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ApprovalRequest]:
    return await approval_service.list_pending(db, brand_id=brand_id, limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalOut)
async def get_approval(
    approval_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> ApprovalRequest:
    return await approval_service.get_or_404(db, approval_id)


@router.post("/{approval_id}/approve", response_model=ApprovalResult)
async def approve(
    approval_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> ApprovalResult:
    approval = await approval_service.get_or_404(db, approval_id)
    if approval.status != ApprovalStatus.pending:
        return ApprovalResult(status=approval.status, detail="Already decided.")

    # Social publish has a dedicated executor that marks the request approved
    # and pushes to the connected platform (Meta / YouTube / X / LinkedIn).
    if approval.action_type == ApprovalAction.social_publish:
        from app.services import social_connection_service
        await social_connection_service.execute_publish(
            db, approval.id, approval.account_id, user
        )
        await write_audit(db, action="approval.approve", user_id=user.id,
                          entity_type="approval", entity_id=str(approval_id),
                          request=request, meta={"action": approval.action_type})
        return ApprovalResult(status="approved")

    await approval_service.mark_approved(db, approval, user_id=user.id)

    sent: int | None = None
    if approval.action_type == ApprovalAction.campaign_send and approval.entity_id:
        sent = await campaign_email_service.execute_send(db, approval.entity_id)
    elif approval.action_type == ApprovalAction.sequence_step_send and approval.entity_id:
        sent = 1 if await sequence_engine.execute_step_run(db, approval.entity_id) else 0

    await write_audit(db, action="approval.approve", user_id=user.id,
                      entity_type="approval", entity_id=str(approval_id),
                      request=request, meta={"action": approval.action_type, "sent": sent})
    return ApprovalResult(status="approved", sent=sent)


@router.post("/{approval_id}/reject", response_model=ApprovalResult)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalDecision,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> ApprovalResult:
    approval = await approval_service.get_or_404(db, approval_id)
    if approval.status != ApprovalStatus.pending:
        return ApprovalResult(status=approval.status, detail="Already decided.")

    await approval_service.mark_rejected(db, approval, user_id=user.id, reason=body.reason)
    if approval.action_type == ApprovalAction.campaign_send and approval.entity_id:
        await campaign_email_service.cancel_pending(db, approval.entity_id)
    elif approval.action_type == ApprovalAction.social_publish and approval.entity_id:
        # Return the post to draft so it can be edited and resubmitted.
        from app.models.content import ContentState
        from app.models.social import SocialPost
        post = await db.get(SocialPost, approval.entity_id)
        if post is not None and post.state == ContentState.needs_review:
            post.state = ContentState.draft
            db.add(post)
            await db.flush()

    await write_audit(db, action="approval.reject", user_id=user.id,
                      entity_type="approval", entity_id=str(approval_id), request=request)
    return ApprovalResult(status="rejected")

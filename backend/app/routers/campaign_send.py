"""Bulk campaign send — approval-first preparation.

Preparing a send builds the recipient messages and raises an ApprovalRequest;
it does NOT send. Sending happens only when an admin approves the request via
the approvals API.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.audit import write_audit
from app.deps import DbSession, require_admin, verify_csrf
from app.models.user import AdminUser
from app.schemas.email import CampaignSendPrepare, CampaignSendResult
from app.services import campaign_email_service, campaign_service

router = APIRouter(prefix="/campaigns", tags=["campaign-send"])


@router.post("/{campaign_id}/email/prepare", response_model=CampaignSendResult)
async def prepare_send(
    campaign_id: uuid.UUID,
    body: CampaignSendPrepare,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> CampaignSendResult:
    campaign = await campaign_service.get_campaign_or_404(db, campaign_id)
    result = await campaign_email_service.prepare_send(
        db, campaign, subject=body.subject, html_body=body.html_body,
        text_body=body.text_body, tag=body.tag, requested_by=user.id,
    )
    await write_audit(db, action="campaign.send_prepare", user_id=user.id,
                      entity_type="campaign", entity_id=str(campaign_id),
                      request=request, meta={"recipients": result["recipient_count"]})
    return CampaignSendResult(**result)

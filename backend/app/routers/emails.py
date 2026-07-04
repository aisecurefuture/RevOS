"""Email messages: list, detail, test send, and preview."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.deps import (
    DbSession,
    require_admin,
    require_authenticated,
    require_editor,
    verify_csrf,
)
from app.models.email import EmailCategory, EmailMessage, EmailStatus
from app.models.user import AdminUser
from app.schemas.email import (
    EmailMessageOut,
    PreviewRequest,
    PreviewResult,
    TestSendRequest,
)
from app.services import email_service, outbox, template_service
from app.services.crud import get_active, list_active

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("", response_model=list[EmailMessageOut])
async def list_messages(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    brand_id: uuid.UUID | None = None,
    status: EmailStatus | None = None,
    campaign_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[EmailMessage]:
    filters: list = []
    if brand_id:
        filters.append(EmailMessage.brand_id == brand_id)
    if status:
        filters.append(EmailMessage.status == status)
    if campaign_id:
        filters.append(EmailMessage.campaign_id == campaign_id)
    return await list_active(db, EmailMessage, filters=filters, limit=limit, offset=offset)


@router.post("/test", response_model=EmailMessageOut)
async def send_test(
    body: TestSendRequest,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_admin)],
    _: None = Depends(verify_csrf),
) -> EmailMessage:
    from_email, from_name = await outbox.resolve_sender(db, body.brand_id)
    message = EmailMessage(
        brand_id=body.brand_id, to_email=str(body.to_email), from_email=from_email,
        from_name=from_name, subject=body.subject, html_body=body.html_body,
        text_body=body.text_body, category=EmailCategory.transactional,
        status=EmailStatus.draft,
    )
    message = await email_service.send_message(db, message)
    await write_audit(db, action="email.test_send", user_id=user.id,
                      entity_type="email", entity_id=str(message.id), request=request)
    return message


@router.post("/preview", response_model=PreviewResult)
async def preview(
    body: PreviewRequest,
    _user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> PreviewResult:
    # Sandboxed, autoescaped render with a sample context merged over user input.
    ctx = {"first_name": "Alex", "brand_name": "Your Brand",
           "unsubscribe_url": "#", **body.context}
    return PreviewResult(
        subject=template_service.render_string(body.subject, ctx),
        html=template_service.render_string(body.html_body, ctx),
    )


@router.get("/{message_id}", response_model=EmailMessageOut)
async def get_message(
    message_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> EmailMessage:
    return await get_active(db, EmailMessage, message_id)

"""Social comment inbox API (approval-gated replies).

The drafted replies live on the Approvals page (action=social_comment_reply);
this router is the comment inbox itself + the like/dismiss actions. Posting a
reply happens through the normal approval approve flow, not here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.core.exceptions import RevOSError
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.user import AdminUser
from app.services import social_comment_service as svc

router = APIRouter(prefix="/social-comments", tags=["social-comments"])


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


class SocialCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    author_name: str | None
    text: str
    permalink: str | None
    status: str
    relevance_note: str | None
    drafted_reply: str | None
    approval_id: uuid.UUID | None
    liked: bool
    posted_at: datetime | None
    created_at: datetime


@router.get("/status")
async def status(_user: Annotated[AdminUser, Depends(require_authenticated)]) -> dict:
    return {"enabled": settings.social_comment_replies_enabled}


@router.get("", response_model=list[SocialCommentOut])
async def list_comments(
    request: Request, db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    status: str | None = None,
) -> list[SocialCommentOut]:
    comments = await svc.list_comments(db, _account_id(request), status=status)
    return [SocialCommentOut.model_validate(c) for c in comments]


@router.post("/{comment_id}/like", response_model=SocialCommentOut)
async def like(
    comment_id: uuid.UUID, request: Request, db: DbSession,
    _user: AdminUser = Depends(require_editor), _c: None = Depends(verify_csrf),
) -> SocialCommentOut:
    comment = await svc.like_comment(db, comment_id, _account_id(request))
    return SocialCommentOut.model_validate(comment)


@router.post("/{comment_id}/dismiss", response_model=SocialCommentOut)
async def dismiss(
    comment_id: uuid.UUID, request: Request, db: DbSession,
    _user: AdminUser = Depends(require_editor), _c: None = Depends(verify_csrf),
) -> SocialCommentOut:
    comment = await svc.set_ignored(db, comment_id, _account_id(request))
    return SocialCommentOut.model_validate(comment)

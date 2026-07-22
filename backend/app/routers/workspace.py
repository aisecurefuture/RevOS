"""Collaboration workspace API (Phase 5 — CW1)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.core.tenancy import get_active_account
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.collaboration import Collaboration, CollaborationShare
from app.models.user import AdminUser
from app.schemas.collaboration import (
    CollaborationOut,
    CollaborationShareOut,
    ShareBrandBookCreate,
    SharedBrandBookOut,
)
from app.schemas.common import Message
from app.services import workspace_service

router = APIRouter(prefix="/matching/workspaces", tags=["collaboration-workspace"])


def _account_id() -> uuid.UUID:
    acct = get_active_account()
    if acct is None:
        raise RevOSError("No active account.", code="no_account", status_code=403)
    return acct


@router.get("", response_model=list[CollaborationOut])
async def list_workspaces(
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    state: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[Collaboration]:
    return await workspace_service.list_collaborations(
        db, _account_id(), state=state, limit=limit, offset=offset)


@router.get("/{collaboration_id}", response_model=CollaborationOut)
async def get_workspace(
    collaboration_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> Collaboration:
    return await workspace_service.get_collaboration(db, collaboration_id, _account_id())


@router.post("/{collaboration_id}/end", response_model=CollaborationOut)
async def end_workspace(
    collaboration_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Collaboration:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    collab = await workspace_service.end_collaboration(db, collab, _account_id())
    await write_audit(db, action="collaboration.ended", user_id=user.id,
                      entity_type="collaboration", entity_id=str(collab.id), request=request)
    return collab


@router.get("/{collaboration_id}/shares", response_model=list[CollaborationShareOut])
async def list_workspace_shares(
    collaboration_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[CollaborationShare]:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    return await workspace_service.list_shares(db, collab, _account_id())


@router.post("/{collaboration_id}/shares/brand-book", response_model=CollaborationShareOut,
             status_code=201)
async def share_brand_book(
    collaboration_id: uuid.UUID,
    body: ShareBrandBookCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationShare:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    share = await workspace_service.share_brand_book(
        db, collab, shared_by_account_id=_account_id(), brand_id=body.brand_id,
        expires_at=body.expires_at)
    await write_audit(db, action="collaboration.share_brand_book", user_id=user.id,
                      entity_type="collaboration_share", entity_id=str(share.id), request=request)
    return share


async def _load_share(db: DbSession, collaboration_id: uuid.UUID,
                      share_id: uuid.UUID) -> CollaborationShare:
    share = await db.get(CollaborationShare, share_id)
    if share is None or share.deleted_at is not None or share.collaboration_id != collaboration_id:
        raise RevOSError("Share not found.", code="not_found", status_code=404)
    return share


@router.delete("/{collaboration_id}/shares/{share_id}", response_model=Message)
async def revoke_share(
    collaboration_id: uuid.UUID,
    share_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> Message:
    await workspace_service.get_collaboration(db, collaboration_id, _account_id())  # party check
    share = await _load_share(db, collaboration_id, share_id)
    await workspace_service.revoke_share(db, share, _account_id())
    await write_audit(db, action="collaboration.revoke_share", user_id=user.id,
                      entity_type="collaboration_share", entity_id=str(share_id), request=request)
    return Message(status="revoked")


@router.get("/{collaboration_id}/shares/{share_id}/brand-book", response_model=SharedBrandBookOut)
async def read_shared_brand_book(
    collaboration_id: uuid.UUID,
    share_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> object:
    await workspace_service.get_collaboration(db, collaboration_id, _account_id())  # party check
    share = await _load_share(db, collaboration_id, share_id)
    return await workspace_service.resolve_shared_brand_book(db, share, _account_id())

"""Collaboration workspace API (Phase 5 — CW1)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.audit import write_audit
from app.core.exceptions import RevOSError
from app.core.tenancy import get_active_account
from app.deps import DbSession, require_authenticated, require_editor, verify_csrf
from app.models.collaboration import (
    Collaboration,
    CollaborationAsset,
    CollaborationDeliverable,
    CollaborationShare,
)
from app.models.user import AdminUser
from app.schemas.collaboration import (
    AssetApprovalOut,
    AssetCommentCreate,
    AssetCommentOut,
    AssetCreate,
    AssetDecisionCreate,
    AssetPublishCreate,
    AssetVersionCreate,
    AssetVersionOut,
    BriefUpsert,
    CollaborationAssetOut,
    CollaborationBriefOut,
    CollaborationOut,
    CollaborationShareOut,
    DeliverableCreate,
    DeliverableOut,
    DeliverableUpdate,
    ShareBrandBookCreate,
    SharedBrandBookOut,
)
from app.schemas.common import Message
from app.schemas.content import SocialPostOut
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


# --- CW2: shared assets + two-sided review-before-post ----------------------
@router.get("/{collaboration_id}/assets", response_model=list[CollaborationAssetOut])
async def list_assets(
    collaboration_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[CollaborationAsset]:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    return await workspace_service.list_assets(db, collab, _account_id())


@router.post("/{collaboration_id}/assets", response_model=CollaborationAssetOut, status_code=201)
async def create_asset(
    collaboration_id: uuid.UUID,
    body: AssetCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationAsset:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    asset = await workspace_service.create_asset(
        db, collab, created_by_account_id=_account_id(), kind=body.kind, title=body.title,
        caption=body.caption, media_urls=body.media_urls)
    await write_audit(db, action="collaboration.asset_create", user_id=user.id,
                      entity_type="collaboration_asset", entity_id=str(asset.id), request=request)
    return asset


async def _load_asset(db: DbSession, collaboration_id: uuid.UUID, asset_id: uuid.UUID,
                      account_id: uuid.UUID) -> tuple[CollaborationAsset, Collaboration]:
    asset, collab = await workspace_service.get_asset(db, asset_id, account_id)
    if asset.collaboration_id != collaboration_id:
        raise RevOSError("Asset not found.", code="not_found", status_code=404)
    return asset, collab


@router.get("/{collaboration_id}/assets/{asset_id}", response_model=CollaborationAssetOut)
async def get_asset(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> CollaborationAsset:
    asset, _collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    return asset


@router.post("/{collaboration_id}/assets/{asset_id}/versions", response_model=AssetVersionOut,
             status_code=201)
async def add_asset_version(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetVersionCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
):
    asset, collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    version = await workspace_service.add_version(
        db, asset, collab, account_id=_account_id(), caption=body.caption, media_urls=body.media_urls)
    await write_audit(db, action="collaboration.asset_new_version", user_id=user.id,
                      entity_type="collaboration_asset", entity_id=str(asset_id), request=request)
    return version


@router.get("/{collaboration_id}/assets/{asset_id}/versions", response_model=list[AssetVersionOut])
async def list_asset_versions(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
):
    asset, _collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    return await workspace_service.list_versions(db, asset)


@router.get("/{collaboration_id}/assets/{asset_id}/comments", response_model=list[AssetCommentOut])
async def list_asset_comments(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
):
    asset, _collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    return await workspace_service.list_comments(db, asset)


@router.post("/{collaboration_id}/assets/{asset_id}/comments", response_model=AssetCommentOut,
             status_code=201)
async def add_asset_comment(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetCommentCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
):
    asset, collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    comment = await workspace_service.add_comment(
        db, asset, collab, account_id=_account_id(), user_id=user.id, body=body.body,
        version=body.version)
    await write_audit(db, action="collaboration.asset_comment", user_id=user.id,
                      entity_type="collaboration_asset", entity_id=str(asset_id), request=request)
    return comment


@router.get("/{collaboration_id}/assets/{asset_id}/approvals", response_model=list[AssetApprovalOut])
async def list_asset_approvals(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
    version: int | None = None,
):
    asset, _collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    return await workspace_service.list_approvals(db, asset, version)


@router.post("/{collaboration_id}/assets/{asset_id}/approve", response_model=CollaborationAssetOut)
async def approve_asset(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetDecisionCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationAsset:
    asset, collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    await workspace_service.approve_asset(
        db, asset, collab, account_id=_account_id(), user_id=user.id, note=body.note)
    await write_audit(db, action="collaboration.asset_approve", user_id=user.id,
                      entity_type="collaboration_asset", entity_id=str(asset_id), request=request)
    return asset


@router.post("/{collaboration_id}/assets/{asset_id}/request-changes", response_model=CollaborationAssetOut)
async def request_asset_changes(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetDecisionCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationAsset:
    asset, collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    await workspace_service.request_changes(
        db, asset, collab, account_id=_account_id(), user_id=user.id, note=body.note)
    await write_audit(db, action="collaboration.asset_request_changes", user_id=user.id,
                      entity_type="collaboration_asset", entity_id=str(asset_id), request=request)
    return asset


@router.post("/{collaboration_id}/assets/{asset_id}/publish", response_model=SocialPostOut)
async def publish_asset(
    collaboration_id: uuid.UUID,
    asset_id: uuid.UUID,
    body: AssetPublishCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
):
    asset, collab = await _load_asset(db, collaboration_id, asset_id, _account_id())
    _asset, post = await workspace_service.publish_asset(
        db, asset, collab, actor_account_id=_account_id(), brand_id=body.brand_id,
        platform=body.platform.value)
    await write_audit(db, action="collaboration.asset_publish", user_id=user.id,
                      entity_type="collaboration_asset", entity_id=str(asset_id), request=request)
    return post


# --- CW3: briefs, deliverables, disclosure & usage rights --------------------
@router.get("/{collaboration_id}/brief", response_model=CollaborationBriefOut | None)
async def get_brief(
    collaboration_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
):
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    return await workspace_service.get_brief(db, collab, _account_id())


@router.put("/{collaboration_id}/brief", response_model=CollaborationBriefOut)
async def upsert_brief(
    collaboration_id: uuid.UUID,
    body: BriefUpsert,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
):
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    brief = await workspace_service.upsert_brief(
        db, collab, account_id=_account_id(), data=body.model_dump())
    await write_audit(db, action="collaboration.brief_update", user_id=user.id,
                      entity_type="collaboration", entity_id=str(collaboration_id), request=request)
    return brief


@router.get("/{collaboration_id}/deliverables", response_model=list[DeliverableOut])
async def list_deliverables(
    collaboration_id: uuid.UUID,
    db: DbSession,
    _user: Annotated[AdminUser, Depends(require_authenticated)],
) -> list[CollaborationDeliverable]:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    return await workspace_service.list_deliverables(db, collab, _account_id())


@router.post("/{collaboration_id}/deliverables", response_model=DeliverableOut, status_code=201)
async def create_deliverable(
    collaboration_id: uuid.UUID,
    body: DeliverableCreate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationDeliverable:
    collab = await workspace_service.get_collaboration(db, collaboration_id, _account_id())
    d = await workspace_service.create_deliverable(
        db, collab, created_by_account_id=_account_id(), title=body.title,
        description=body.description, due_at=body.due_at)
    await write_audit(db, action="collaboration.deliverable_create", user_id=user.id,
                      entity_type="collaboration_deliverable", entity_id=str(d.id), request=request)
    return d


async def _load_deliverable(db: DbSession, collaboration_id: uuid.UUID, deliverable_id: uuid.UUID,
                            account_id: uuid.UUID) -> tuple[CollaborationDeliverable, Collaboration]:
    d, collab = await workspace_service.get_deliverable(db, deliverable_id, account_id)
    if d.collaboration_id != collaboration_id:
        raise RevOSError("Deliverable not found.", code="not_found", status_code=404)
    return d, collab


@router.patch("/{collaboration_id}/deliverables/{deliverable_id}", response_model=DeliverableOut)
async def update_deliverable(
    collaboration_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    body: DeliverableUpdate,
    request: Request,
    db: DbSession,
    user: Annotated[AdminUser, Depends(require_editor)],
    _: None = Depends(verify_csrf),
) -> CollaborationDeliverable:
    d, collab = await _load_deliverable(db, collaboration_id, deliverable_id, _account_id())
    d = await workspace_service.update_deliverable(
        db, d, collab, account_id=_account_id(), data=body.model_dump(exclude_unset=True))
    await write_audit(db, action="collaboration.deliverable_update", user_id=user.id,
                      entity_type="collaboration_deliverable", entity_id=str(deliverable_id),
                      request=request)
    return d

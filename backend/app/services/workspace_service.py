"""Collaboration workspace service (Phase 5 — CW1).

Spawns a Collaboration when a request is accepted, and runs the consent-gated,
time-boxed knowledge-sharing model: a party grants the other read access to a
resource (v1: a Brand Book) within a collaboration; access is revocable,
expirable, and auto-revoked when the collaboration ends.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import or_, select

from app.core.exceptions import RevOSError
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.brand_book import BrandBook
from app.models.collaboration import (
    ApprovalDecision,
    AssetState,
    Collaboration,
    CollaborationAsset,
    CollaborationAssetApproval,
    CollaborationAssetComment,
    CollaborationAssetVersion,
    CollaborationShare,
    CollaborationState,
    ShareStatus,
    SharedResourceType,
)
from app.models.matching import CollaborationDirection, CollaborationRequest


# --- Spawn on acceptance ----------------------------------------------------
async def spawn_collaboration(db: AsyncSession, request: CollaborationRequest) -> Collaboration:
    """Idempotently create the workspace for an accepted request."""
    existing = (await db.execute(
        select(Collaboration).where(Collaboration.collaboration_request_id == request.id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    if request.direction == CollaborationDirection.brand_to_creator:
        brand_account, creator_account = request.initiator_account_id, request.recipient_account_id
    else:
        creator_account, brand_account = request.initiator_account_id, request.recipient_account_id

    collab = Collaboration(
        collaboration_request_id=request.id,
        brand_account_id=brand_account, creator_account_id=creator_account,
        creator_id=request.creator_id, product_id=request.product_id,
    )
    db.add(collab)
    await db.flush()
    await db.refresh(collab)
    return collab


def _parties(collab: Collaboration) -> set[uuid.UUID]:
    return {collab.brand_account_id, collab.creator_account_id}


def _require_party(collab: Collaboration, account_id: uuid.UUID) -> None:
    if account_id not in _parties(collab):
        raise RevOSError("You are not a party to this collaboration.", code="forbidden", status_code=403)


# --- Collaboration reads ----------------------------------------------------
async def get_collaboration(db: AsyncSession, collaboration_id: uuid.UUID,
                            account_id: uuid.UUID) -> Collaboration:
    collab = await db.get(Collaboration, collaboration_id)
    if collab is None or collab.deleted_at is not None:
        raise RevOSError("Collaboration not found.", code="not_found", status_code=404)
    _require_party(collab, account_id)
    return collab


async def list_collaborations(db: AsyncSession, account_id: uuid.UUID, *,
                              state: str | None = None, limit: int = 50, offset: int = 0
                              ) -> list[Collaboration]:
    stmt = select(Collaboration).where(
        or_(Collaboration.brand_account_id == account_id,
            Collaboration.creator_account_id == account_id),
        Collaboration.deleted_at.is_(None))
    if state:
        stmt = stmt.where(Collaboration.state == state)
    stmt = stmt.order_by(Collaboration.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def end_collaboration(db: AsyncSession, collab: Collaboration,
                            actor_account_id: uuid.UUID) -> Collaboration:
    _require_party(collab, actor_account_id)
    collab.state = CollaborationState.ended
    collab.ended_at = utcnow()
    db.add(collab)
    # Consent guarantee: ending the collaboration auto-revokes every active share.
    shares = (await db.execute(select(CollaborationShare).where(
        CollaborationShare.collaboration_id == collab.id,
        CollaborationShare.status == ShareStatus.active))).scalars().all()
    for s in shares:
        s.status = ShareStatus.revoked
        s.revoked_at = utcnow()
        db.add(s)
    await db.flush()
    await db.refresh(collab)
    return collab


# --- Sharing ----------------------------------------------------------------
async def share_brand_book(db: AsyncSession, collab: Collaboration, *,
                           shared_by_account_id: uuid.UUID, brand_id: uuid.UUID,
                           expires_at=None) -> CollaborationShare:
    _require_party(collab, shared_by_account_id)
    if collab.state == CollaborationState.ended:
        raise RevOSError("This collaboration has ended.", code="collaboration_ended", status_code=409)

    brand = await db.get(Brand, brand_id)
    if brand is None or brand.account_id != shared_by_account_id:
        raise RevOSError("You can only share your own brand's book.", code="forbidden", status_code=403)
    book = (await db.execute(select(BrandBook).where(BrandBook.brand_id == brand_id))).scalar_one_or_none()
    if book is None:
        raise RevOSError("That brand has no Brand Book to share yet.", code="no_brand_book", status_code=400)

    # Idempotent + re-activatable (the unique constraint ignores status).
    existing = (await db.execute(select(CollaborationShare).where(
        CollaborationShare.collaboration_id == collab.id,
        CollaborationShare.resource_type == SharedResourceType.brand_book,
        CollaborationShare.resource_id == brand_id,
        CollaborationShare.shared_by_account_id == shared_by_account_id))).scalar_one_or_none()
    if existing is not None:
        existing.status = ShareStatus.active
        existing.revoked_at = None
        existing.expires_at = expires_at
        db.add(existing)
        await db.flush()
        await db.refresh(existing)
        return existing

    share = CollaborationShare(
        collaboration_id=collab.id, shared_by_account_id=shared_by_account_id,
        resource_type=SharedResourceType.brand_book, resource_id=brand_id, expires_at=expires_at)
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return share


async def revoke_share(db: AsyncSession, share: CollaborationShare,
                       actor_account_id: uuid.UUID) -> CollaborationShare:
    if share.shared_by_account_id != actor_account_id:
        raise RevOSError("Only the party who shared this can revoke it.", code="forbidden", status_code=403)
    share.status = ShareStatus.revoked
    share.revoked_at = utcnow()
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return share


async def list_shares(db: AsyncSession, collab: Collaboration,
                      viewer_account_id: uuid.UUID) -> list[CollaborationShare]:
    _require_party(collab, viewer_account_id)
    rows = (await db.execute(select(CollaborationShare).where(
        CollaborationShare.collaboration_id == collab.id,
        CollaborationShare.deleted_at.is_(None)).order_by(
        CollaborationShare.created_at.desc()))).scalars().all()
    return [_lazy_expire(s) for s in rows]


def _lazy_expire(share: CollaborationShare) -> CollaborationShare:
    if share.status == ShareStatus.active and share.expires_at and share.expires_at < utcnow():
        share.status = ShareStatus.expired
    return share


async def resolve_shared_brand_book(db: AsyncSession, share: CollaborationShare,
                                    viewer_account_id: uuid.UUID) -> BrandBook:
    """The consumer view — read the Brand Book a party shared. Gated on: viewer
    is a party, the share is live (not revoked/expired), and the collaboration
    hasn't ended."""
    collab = await db.get(Collaboration, share.collaboration_id)
    if collab is None:
        raise RevOSError("Collaboration not found.", code="not_found", status_code=404)
    _require_party(collab, viewer_account_id)
    if collab.state == CollaborationState.ended:
        raise RevOSError("This collaboration has ended — sharing is closed.",
                         code="collaboration_ended", status_code=403)
    _lazy_expire(share)
    if share.status != ShareStatus.active:
        raise RevOSError(f"This share is {share.status}.", code="share_inactive", status_code=403)
    if share.resource_type != SharedResourceType.brand_book:
        raise RevOSError("Unsupported shared resource.", code="unsupported_resource", status_code=400)

    book = (await db.execute(select(BrandBook).where(
        BrandBook.brand_id == share.resource_id))).scalar_one_or_none()
    if book is None:
        raise RevOSError("The shared Brand Book no longer exists.", code="not_found", status_code=404)
    return book


# --- CW2: shared assets + two-sided review-before-post ----------------------
async def create_asset(db: AsyncSession, collab: Collaboration, *,
                       created_by_account_id: uuid.UUID, kind, title: str | None,
                       caption: str | None, media_urls: list[str]) -> CollaborationAsset:
    _require_party(collab, created_by_account_id)
    if collab.state == CollaborationState.ended:
        raise RevOSError("This collaboration has ended.", code="collaboration_ended", status_code=409)

    asset = CollaborationAsset(
        collaboration_id=collab.id, created_by_account_id=created_by_account_id,
        kind=kind, title=title, current_version=1, state=AssetState.draft)
    db.add(asset)
    await db.flush()
    db.add(CollaborationAssetVersion(
        asset_id=asset.id, version=1, created_by_account_id=created_by_account_id,
        caption=caption, media_urls=media_urls))
    await db.flush()
    await db.refresh(asset)
    return asset


async def get_asset(db: AsyncSession, asset_id: uuid.UUID, account_id: uuid.UUID
                    ) -> tuple[CollaborationAsset, Collaboration]:
    asset = await db.get(CollaborationAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise RevOSError("Asset not found.", code="not_found", status_code=404)
    collab = await db.get(Collaboration, asset.collaboration_id)
    _require_party(collab, account_id)
    return asset, collab


async def list_assets(db: AsyncSession, collab: Collaboration, account_id: uuid.UUID
                      ) -> list[CollaborationAsset]:
    _require_party(collab, account_id)
    stmt = select(CollaborationAsset).where(
        CollaborationAsset.collaboration_id == collab.id, CollaborationAsset.deleted_at.is_(None),
    ).order_by(CollaborationAsset.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def add_version(db: AsyncSession, asset: CollaborationAsset, collab: Collaboration, *,
                      account_id: uuid.UUID, caption: str | None, media_urls: list[str]
                      ) -> CollaborationAssetVersion:
    """A new draft always needs fresh sign-off — approvals are recorded against
    a specific version, so bumping the version implicitly invalidates them
    without touching a single existing approval row."""
    _require_party(collab, account_id)
    if collab.state == CollaborationState.ended:
        raise RevOSError("This collaboration has ended.", code="collaboration_ended", status_code=409)
    if asset.state == AssetState.published:
        raise RevOSError("This asset has already been published.", code="already_published", status_code=409)

    asset.current_version += 1
    asset.state = AssetState.draft
    db.add(asset)
    version = CollaborationAssetVersion(
        asset_id=asset.id, version=asset.current_version,
        created_by_account_id=account_id, caption=caption, media_urls=media_urls)
    db.add(version)
    await db.flush()
    await db.refresh(version)
    return version


async def list_versions(db: AsyncSession, asset: CollaborationAsset) -> list[CollaborationAssetVersion]:
    stmt = select(CollaborationAssetVersion).where(
        CollaborationAssetVersion.asset_id == asset.id,
    ).order_by(CollaborationAssetVersion.version.desc())
    return list((await db.execute(stmt)).scalars().all())


async def add_comment(db: AsyncSession, asset: CollaborationAsset, collab: Collaboration, *,
                      account_id: uuid.UUID, user_id: uuid.UUID, body: str,
                      version: int | None = None) -> CollaborationAssetComment:
    _require_party(collab, account_id)
    comment = CollaborationAssetComment(
        asset_id=asset.id, version=version, author_account_id=account_id,
        author_user_id=user_id, body=body.strip())
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment


async def list_comments(db: AsyncSession, asset: CollaborationAsset) -> list[CollaborationAssetComment]:
    stmt = select(CollaborationAssetComment).where(
        CollaborationAssetComment.asset_id == asset.id, CollaborationAssetComment.deleted_at.is_(None),
    ).order_by(CollaborationAssetComment.created_at.asc())
    return list((await db.execute(stmt)).scalars().all())


async def _decide(db: AsyncSession, asset: CollaborationAsset, collab: Collaboration, *,
                  account_id: uuid.UUID, user_id: uuid.UUID, decision: ApprovalDecision,
                  note: str | None) -> CollaborationAssetApproval:
    _require_party(collab, account_id)
    if collab.state == CollaborationState.ended:
        raise RevOSError("This collaboration has ended.", code="collaboration_ended", status_code=409)
    if asset.state == AssetState.published:
        raise RevOSError("This asset has already been published.", code="already_published", status_code=409)

    existing = (await db.execute(select(CollaborationAssetApproval).where(
        CollaborationAssetApproval.asset_id == asset.id,
        CollaborationAssetApproval.version == asset.current_version,
        CollaborationAssetApproval.account_id == account_id))).scalar_one_or_none()
    if existing is not None:
        existing.decision = decision
        existing.note = note
        existing.user_id = user_id
        db.add(existing)
        approval = existing
    else:
        approval = CollaborationAssetApproval(
            asset_id=asset.id, version=asset.current_version, account_id=account_id,
            user_id=user_id, decision=decision, note=note)
        db.add(approval)
    await db.flush()

    if decision == ApprovalDecision.changes_requested:
        asset.state = AssetState.changes_requested
    else:
        decisions = (await db.execute(select(CollaborationAssetApproval).where(
            CollaborationAssetApproval.asset_id == asset.id,
            CollaborationAssetApproval.version == asset.current_version))).scalars().all()
        both_approved = (
            {d.account_id for d in decisions if d.decision == ApprovalDecision.approved}
            >= _parties(collab)
        )
        asset.state = AssetState.approved if both_approved else AssetState.in_review
    db.add(asset)
    await db.flush()
    await db.refresh(approval)
    return approval


async def approve_asset(db, asset, collab, *, account_id, user_id, note=None):
    return await _decide(db, asset, collab, account_id=account_id, user_id=user_id,
                         decision=ApprovalDecision.approved, note=note)


async def request_changes(db, asset, collab, *, account_id, user_id, note=None):
    return await _decide(db, asset, collab, account_id=account_id, user_id=user_id,
                         decision=ApprovalDecision.changes_requested, note=note)


async def list_approvals(db: AsyncSession, asset: CollaborationAsset,
                         version: int | None = None) -> list[CollaborationAssetApproval]:
    stmt = select(CollaborationAssetApproval).where(
        CollaborationAssetApproval.asset_id == asset.id,
        CollaborationAssetApproval.version == (version or asset.current_version))
    return list((await db.execute(stmt)).scalars().all())


async def publish_asset(db: AsyncSession, asset: CollaborationAsset, collab: Collaboration, *,
                        actor_account_id: uuid.UUID, brand_id: uuid.UUID, platform: str):
    """Hand off an approved asset into the real content/social publishing +
    approval pipeline. Only the CREATOR side may do this — it's their own
    social account that will post. The caller is already authenticated as
    themselves, so the resulting SocialPost is correctly tenant-stamped to the
    creator's own account by the normal before_flush hook; no cross-tenant
    write is needed."""
    from app.services import social_service
    from app.services.crud import get_active

    if actor_account_id != collab.creator_account_id:
        raise RevOSError("Only the creator can publish this asset to their own account.",
                         code="forbidden", status_code=403)
    if asset.state != AssetState.approved:
        raise RevOSError("Both parties must approve the current version before publishing.",
                         code="not_approved", status_code=409)

    brand = await get_active(db, Brand, brand_id)   # tenant-scoped: must be the actor's own brand
    version = (await db.execute(select(CollaborationAssetVersion).where(
        CollaborationAssetVersion.asset_id == asset.id,
        CollaborationAssetVersion.version == asset.current_version))).scalar_one()

    post = await social_service.create_post(db, {
        "brand_id": brand.id, "platform": platform,
        "caption": version.caption, "media_urls": version.media_urls,
    })
    asset.state = AssetState.published
    asset.linked_social_post_id = post.id
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return asset, post

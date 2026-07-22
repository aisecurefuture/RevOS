"""Collaboration request workflow (Phase 3, MK2).

Structured, spam-controlled outreach between brands and creators, either side
initiating. Cross-tenant: requests carry explicit initiator/recipient account
ids and are queried per-side (never auto-scoped).

Anti-spam is structural: one message per request, hard caps on pending/daily
volume per account, and de-duplication. Free-form messaging only exists after
acceptance (a later module) — there is no cold-DM surface here.

Responses arrive through three channels, all landing on ``respond()``:
  1. emailed signed accept/decline links (``respond_via_token``) — no login
  2. the recipient tenant/agency accepting in-app (authenticated)
  3. a creator portal (later) — same path
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.exceptions import RevOSError
from app.core.security import make_signed_token, read_signed_token
from app.models.base import utcnow
from app.models.matching import (
    CollaborationDirection,
    CollaborationRequest,
    CollaborationStatus,
    Creator,
    MatchProduct,
)
from app.services.account_service import get_personal_account

_RESPOND_SALT = "collab-respond"
EXPIRY_DAYS = 14
MAX_PENDING_PER_ACCOUNT = 50        # outstanding pending requests an account may have
MAX_REQUESTS_PER_DAY = 25           # requests an account may create in 24h
_RESPOND_MAX_AGE = 60 * 60 * 24 * EXPIRY_DAYS


# --- Response tokens (emailed accept/decline links) -------------------------
def make_respond_url(request_id: uuid.UUID, accept: bool) -> str:
    token = make_signed_token(
        {"req": str(request_id), "action": "accept" if accept else "decline"},
        salt=_RESPOND_SALT,
    )
    return f"{settings.public_base_url}/api/public/collab/respond?token={token}"


# --- Creating a request -----------------------------------------------------
async def _count(db: AsyncSession, *conds) -> int:
    stmt = select(func.count()).select_from(CollaborationRequest).where(*conds)
    return int((await db.execute(stmt)).scalar_one())


async def create_request(
    db: AsyncSession, *,
    initiator_account_id: uuid.UUID,
    initiator_user_id: uuid.UUID,
    direction: CollaborationDirection,
    creator_id: uuid.UUID,
    product_id: uuid.UUID | None,
    message: str,
    brokered_by_user_id: uuid.UUID | None = None,
) -> CollaborationRequest:
    broker = brokered_by_user_id is not None

    creator = await db.get(Creator, creator_id)
    if creator is None or creator.deleted_at is not None:
        raise RevOSError("Creator not found.", code="not_found", status_code=404)
    product = await db.get(MatchProduct, product_id) if product_id else None

    # Once a creator claims their profile, NEW requests route to their own
    # account — the agency keeps its history (past collaborations, reviews,
    # certs) untouched but no longer fields fresh requests for this creator.
    creator_party_account_id = creator.account_id
    if creator.claimed_by_user_id is not None:
        personal = await get_personal_account(db, creator.claimed_by_user_id)
        if personal is not None:
            creator_party_account_id = personal.id

    if direction == CollaborationDirection.brand_to_creator:
        if product is None:
            raise RevOSError("A product is required to reach out to a creator.",
                             code="product_required", status_code=400)
        if not broker and product.account_id != initiator_account_id:
            raise RevOSError("You can only reach out with your own product.",
                             code="forbidden", status_code=403)
        cross_tenant = creator_party_account_id != initiator_account_id
        if cross_tenant and not broker and not creator.discoverable:
            raise RevOSError("This creator is not open to marketplace requests.",
                             code="not_discoverable", status_code=403)
        recipient_account_id = creator_party_account_id
    else:  # creator_to_brand
        # Either the agency that manages this creator, or the creator
        # themselves once they've claimed the profile, may reach out on
        # their behalf.
        is_agency = creator.account_id == initiator_account_id
        is_claimed_self = (creator.claimed_by_user_id is not None
                           and creator.claimed_by_user_id == initiator_user_id)
        if not broker and not is_agency and not is_claimed_self:
            raise RevOSError("You can only reach out on behalf of your own creator.",
                             code="forbidden", status_code=403)
        if product is None:
            raise RevOSError("A target product is required.", code="product_required", status_code=400)
        cross_tenant = product.account_id != initiator_account_id
        if cross_tenant and not broker and not product.discoverable:
            raise RevOSError("This product is not open to marketplace requests.",
                             code="not_discoverable", status_code=403)
        recipient_account_id = product.account_id

    # Anti-spam: caps + de-dup (brokered requests bypass the volume caps).
    if not broker:
        pending = await _count(
            db, CollaborationRequest.initiator_account_id == initiator_account_id,
            CollaborationRequest.status == CollaborationStatus.pending,
            CollaborationRequest.deleted_at.is_(None),
        )
        if pending >= MAX_PENDING_PER_ACCOUNT:
            raise RevOSError("You have too many pending requests. Wait for responses first.",
                             code="rate_limited", status_code=429)
        today = await _count(
            db, CollaborationRequest.initiator_account_id == initiator_account_id,
            CollaborationRequest.created_at >= utcnow() - timedelta(days=1),
        )
        if today >= MAX_REQUESTS_PER_DAY:
            raise RevOSError("Daily request limit reached. Try again tomorrow.",
                             code="rate_limited", status_code=429)

    dupe = await _count(
        db,
        CollaborationRequest.initiator_account_id == initiator_account_id,
        CollaborationRequest.creator_id == creator_id,
        CollaborationRequest.product_id == product_id,
        CollaborationRequest.direction == direction,
        CollaborationRequest.status == CollaborationStatus.pending,
        CollaborationRequest.deleted_at.is_(None),
    )
    if dupe:
        raise RevOSError("You already have a pending request for this pairing.",
                         code="duplicate_request", status_code=409)

    req = CollaborationRequest(
        direction=direction, status=CollaborationStatus.pending,
        initiator_account_id=initiator_account_id, initiator_user_id=initiator_user_id,
        creator_id=creator_id, product_id=product_id,
        recipient_account_id=recipient_account_id, message=message.strip(),
        brokered_by_user_id=brokered_by_user_id,
        expires_at=utcnow() + timedelta(days=EXPIRY_DAYS),
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)
    return req


# --- Responding -------------------------------------------------------------
async def respond(
    db: AsyncSession, request: CollaborationRequest, *,
    accept: bool, note: str | None = None, channel: str = "in_app",
) -> CollaborationRequest:
    if request.status != CollaborationStatus.pending:
        raise RevOSError(f"This request is already {request.status}.",
                         code="not_pending", status_code=409)
    if request.expires_at and request.expires_at < utcnow():
        request.status = CollaborationStatus.expired
        await db.flush()
        raise RevOSError("This request has expired.", code="request_expired", status_code=410)
    request.status = CollaborationStatus.accepted if accept else CollaborationStatus.declined
    request.responded_at = utcnow()
    request.response_note = note
    request.response_channel = channel
    db.add(request)
    await db.flush()
    await db.refresh(request)
    if accept:
        # Acceptance opens the shared workspace (CW1).
        from app.services import workspace_service
        await workspace_service.spawn_collaboration(db, request)
    return request


async def withdraw(
    db: AsyncSession, request: CollaborationRequest, *, actor_account_id: uuid.UUID,
) -> CollaborationRequest:
    if request.initiator_account_id != actor_account_id:
        raise RevOSError("Only the sender can withdraw a request.", code="forbidden", status_code=403)
    if request.status != CollaborationStatus.pending:
        raise RevOSError(f"This request is already {request.status}.", code="not_pending", status_code=409)
    request.status = CollaborationStatus.withdrawn
    request.responded_at = utcnow()
    db.add(request)
    await db.flush()
    await db.refresh(request)
    return request


async def respond_via_token(db: AsyncSession, token: str) -> CollaborationRequest:
    data = read_signed_token(token, salt=_RESPOND_SALT, max_age_seconds=_RESPOND_MAX_AGE)
    request = await db.get(CollaborationRequest, uuid.UUID(data["req"]))
    if request is None or request.deleted_at is not None:
        raise RevOSError("This request link is no longer valid.", code="not_found", status_code=404)
    return await respond(db, request, accept=data["action"] == "accept", channel="email")


# --- Inboxes ----------------------------------------------------------------
async def list_for_account(
    db: AsyncSession, account_id: uuid.UUID, *, box: str = "incoming",
    status: str | None = None, limit: int = 50, offset: int = 0,
) -> list[CollaborationRequest]:
    """box='incoming' → requests awaiting this account's response;
    box='outgoing' → requests this account sent."""
    side = (CollaborationRequest.recipient_account_id == account_id if box == "incoming"
            else CollaborationRequest.initiator_account_id == account_id)
    stmt = select(CollaborationRequest).where(side, CollaborationRequest.deleted_at.is_(None))
    if status:
        stmt = stmt.where(CollaborationRequest.status == status)
    stmt = stmt.order_by(CollaborationRequest.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def expire_due(db: AsyncSession) -> int:
    """Mark pending requests past their expiry as expired (beat-driven)."""
    stmt = select(CollaborationRequest).where(
        CollaborationRequest.status == CollaborationStatus.pending,
        CollaborationRequest.expires_at.is_not(None),
        CollaborationRequest.expires_at < utcnow(),
    ).limit(500)
    due = list((await db.execute(stmt)).scalars().all())
    for req in due:
        req.status = CollaborationStatus.expired
        db.add(req)
    await db.flush()
    return len(due)

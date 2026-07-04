"""Social OAuth router — Phase 2 M5.

Endpoints:
  GET  /api/social/{platform}/connect          — start OAuth flow (redirect)
  GET  /api/social/{platform}/callback         — OAuth callback (exchange + store)
  GET  /api/social/connections                 — list account connections
  DELETE /api/social/connections/{id}          — disconnect (revoke token)
  POST /api/social/posts/{post_id}/submit      — submit for approval
  POST /api/social/approvals/{id}/publish      — approve + publish (owner only)
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from app.core.exceptions import RevOSError
from app.deps import CurrentUser, DbSession, require_owner, verify_csrf
from app.models.user import AdminUser
from app.schemas.social_connection import (
    ConnectUrlOut,
    SocialConnectionOut,
    SubmitForApprovalOut,
)
from app.services import social_connection_service as svc
from app.config import settings

logger = logging.getLogger("revos.social_oauth")
router = APIRouter(prefix="/social", tags=["social-oauth"])

_SUPPORTED_PLATFORMS = {"facebook", "instagram"}


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


# ---------------------------------------------------------------------------
# OAuth connect — returns redirect URL (frontend can window.location it)
# ---------------------------------------------------------------------------

@router.get("/connections/connect-url")
async def get_connect_url(
    request: Request,
    platform: str,
    user: CurrentUser,
) -> ConnectUrlOut:
    """Return the Meta OAuth dialog URL. Frontend redirects the user there."""
    account_id = _account_id(request)
    url = svc.get_connect_url(platform, account_id)
    return ConnectUrlOut(url=url)


# ---------------------------------------------------------------------------
# OAuth callback — called by Meta after user authorises
# ---------------------------------------------------------------------------

@router.get("/{platform}/callback", include_in_schema=False)
async def oauth_callback(
    platform: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_reason: str | None = None,
    db: DbSession = None,
    user: CurrentUser = None,
) -> RedirectResponse:
    """Meta redirects here after the OAuth dialog.

    On success: redirects to frontend /dashboard/settings/connections?connected={platform}
    On error:   redirects to frontend /dashboard/settings/connections?error={reason}
    """
    base = settings.frontend_base_url
    dest_ok = f"{base}/dashboard/settings/connections?connected={platform}"
    dest_err = f"{base}/dashboard/settings/connections?error=oauth_failed"

    if error or not code or not state:
        reason = error_reason or error or "cancelled"
        logger.info("Meta OAuth denied: %s", reason)
        return RedirectResponse(f"{base}/dashboard/settings/connections?error={reason}")

    if platform not in _SUPPORTED_PLATFORMS:
        return RedirectResponse(f"{dest_err}&detail=unsupported_platform")

    try:
        connections = await svc.handle_meta_callback(
            code=code,
            state=state,
            user=user,
            db=db,
        )
        logger.info("Meta OAuth: created %d connection(s) for user %s", len(connections), user.id)
        return RedirectResponse(f"{dest_ok}&count={len(connections)}")
    except RevOSError as exc:
        logger.warning("Meta OAuth callback error: %s", exc.message)
        return RedirectResponse(f"{dest_err}&detail={exc.code}")
    except Exception as exc:
        logger.error("Unexpected OAuth callback error: %s", exc, exc_info=True)
        return RedirectResponse(dest_err)


# ---------------------------------------------------------------------------
# List connections
# ---------------------------------------------------------------------------

@router.get("/connections", response_model=list[SocialConnectionOut])
async def list_connections(
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> list[SocialConnectionOut]:
    account_id = _account_id(request)
    conns = await svc.list_connections(db, account_id)
    return [
        SocialConnectionOut(
            id=c.id,
            account_id=c.account_id,
            platform=c.platform,
            external_id=c.external_id,
            handle=c.handle,
            display_name=c.display_name,
            scopes=c.scopes,
            status=c.status,
            connected_by=c.connected_by,
            expires_at=c.expires_at,
            platform_meta=c.platform_meta,
            created_at=c.created_at,
        )
        for c in conns
    ]


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

@router.delete("/connections/{connection_id}", status_code=204)
async def disconnect(
    connection_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _csrf: None = Depends(verify_csrf),
) -> Response:
    account_id = _account_id(request)
    await svc.disconnect(db, connection_id, account_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Submit for approval
# ---------------------------------------------------------------------------

@router.post("/posts/{post_id}/submit", response_model=SubmitForApprovalOut)
async def submit_post(
    post_id: uuid.UUID,
    connection_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _csrf: None = Depends(verify_csrf),
) -> SubmitForApprovalOut:
    """Submit a SocialPost for publish approval.

    Returns the created ApprovalRequest ID. An owner must then approve it
    via POST /social/approvals/{id}/publish.
    """
    account_id = _account_id(request)
    req = await svc.submit_for_approval(db, post_id, connection_id, account_id, user)
    return SubmitForApprovalOut(
        approval_request_id=req.id,
        message="Post submitted for approval. An owner must approve before publishing.",
    )


# ---------------------------------------------------------------------------
# Approve + publish (owner only)
# ---------------------------------------------------------------------------

@router.post("/approvals/{approval_id}/publish")
async def approve_and_publish(
    approval_id: uuid.UUID,
    request: Request,
    user: AdminUser = Depends(require_owner),
    db: DbSession = None,
    _csrf: None = Depends(verify_csrf),
) -> dict:
    """Approve an approval request and immediately publish the post.

    Owner-only. CSRF-protected.
    """
    account_id = _account_id(request)
    post = await svc.execute_publish(db, approval_id, account_id, user)
    return {
        "published": True,
        "post_id": str(post.id),
        "external_post_id": post.external_post_id,
        "platform": post.platform,
    }

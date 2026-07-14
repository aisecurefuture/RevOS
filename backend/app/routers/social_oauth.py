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

import base64
import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse

from app.core.exceptions import RevOSError
from app.deps import CurrentUser, DbSession, require_owner, require_verified_email, verify_csrf
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

_SUPPORTED_PLATFORMS = {"facebook", "instagram", "threads", "youtube", "twitter", "linkedin", "tiktok"}


def _account_id(request: Request) -> uuid.UUID:
    acc = getattr(request.state, "account_id", None)
    if acc is None:
        raise RevOSError("No active account.", code="no_account", status_code=400)
    return acc


# ---------------------------------------------------------------------------
# Meta data-deletion callback
# ---------------------------------------------------------------------------

def _parse_meta_signed_request(signed_request: str, app_secret: str) -> dict:
    """Validate and decode a Meta signed_request parameter."""
    try:
        encoded_sig, payload = signed_request.split(".", 1)
        sig = base64.urlsafe_b64decode(encoded_sig + "==")
        data = json.loads(base64.urlsafe_b64decode(payload + "==").decode("utf-8"))
        expected = hmac.new(
            app_secret.encode("utf-8"),
            msg=payload.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Signature mismatch")
        return data
    except Exception as exc:
        raise ValueError(f"Invalid signed_request: {exc}") from exc


@router.post("/data-deletion", include_in_schema=False)
async def meta_data_deletion(
    signed_request: str = Form(...),
    db: DbSession = None,
) -> dict:
    """Meta calls this endpoint when a user removes the RevOS app from their
    Facebook settings. We delete all associated social connections and tokens.

    https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback
    """
    if not settings.meta_app_secret:
        logger.error("META_APP_SECRET not configured — cannot process data-deletion callback")
        return Response(status_code=400)

    try:
        data = _parse_meta_signed_request(signed_request, settings.meta_app_secret)
    except ValueError as exc:
        logger.warning("Data-deletion: invalid signed_request — %s", exc)
        return Response(status_code=400)

    facebook_user_id = data.get("user_id", "")
    confirmation_code = str(uuid.uuid4())

    if facebook_user_id and db is not None:
        count = await svc.delete_connections_by_facebook_user_id(db, facebook_user_id)
        logger.info(
            "Meta data-deletion: deleted %d connection(s) for fb_user_id=%s code=%s",
            count, facebook_user_id, confirmation_code,
        )

    return {
        "url": f"{settings.frontend_base_url}/data-deletion?code={confirmation_code}",
        "confirmation_code": confirmation_code,
    }


# ---------------------------------------------------------------------------
# OAuth connect — returns redirect URL (frontend can window.location it)
# ---------------------------------------------------------------------------

@router.get("/connections/connect-url")
async def get_connect_url(
    request: Request,
    platform: str,
    user: CurrentUser,
    _verified: AdminUser = Depends(require_verified_email),
) -> ConnectUrlOut:
    """Return the Meta OAuth dialog URL. Frontend redirects the user there."""
    account_id = _account_id(request)
    # user.id is signed into the OAuth state so the callback can identify the
    # connector without the session cookie (the provider redirects to a
    # different subdomain where the cookie isn't sent).
    url = svc.get_connect_url(platform, account_id, user.id)
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
) -> RedirectResponse:
    """The provider redirects here after the OAuth dialog.

    NOTE: this endpoint does NOT require the session cookie. It's a cross-site
    redirect from the provider to the api.* subdomain, where the app.* session
    cookie isn't sent — so we authenticate the connecting user from the
    HMAC-signed, time-limited `state` instead (minted by an authenticated
    connect-url call). This is the standard OAuth-callback pattern.

    On success: redirects to frontend /dashboard/settings/connections?connected={platform}
    On error:   redirects to frontend /dashboard/settings/connections?error={reason}
    """
    base = settings.frontend_base_url
    dest_ok = f"{base}/dashboard/settings/connections?connected={platform}"
    dest_err = f"{base}/dashboard/settings/connections?error=oauth_failed"

    if error or not code or not state:
        reason = error_reason or error or "cancelled"
        logger.info("OAuth denied: %s", reason)
        return RedirectResponse(f"{base}/dashboard/settings/connections?error={reason}")

    if platform not in _SUPPORTED_PLATFORMS:
        return RedirectResponse(f"{dest_err}&detail=unsupported_platform")

    try:
        # Identify the connecting user from the signed state (not the cookie).
        user = await svc.resolve_state_user(db, svc.verify_oauth_state(state))
        if platform == "threads":
            connections = await svc.handle_threads_callback(
                code=code, state=state, user=user, db=db,
            )
            logger.info("Threads OAuth: created %d connection(s) for user %s", len(connections), user.id)
        elif platform == "youtube":
            connections = await svc.handle_youtube_callback(
                code=code, state=state, user=user, db=db,
            )
            logger.info("YouTube OAuth: created %d connection(s) for user %s", len(connections), user.id)
        elif platform == "twitter":
            connections = await svc.handle_x_callback(
                code=code, state=state, user=user, db=db,
            )
            logger.info("X OAuth: created %d connection(s) for user %s", len(connections), user.id)
        elif platform == "linkedin":
            connections = await svc.handle_linkedin_callback(
                code=code, state=state, user=user, db=db,
            )
            logger.info("LinkedIn OAuth: created %d connection(s) for user %s", len(connections), user.id)
        elif platform == "tiktok":
            connections = await svc.handle_tiktok_callback(
                code=code, state=state, user=user, db=db,
            )
            logger.info("TikTok OAuth: created %d connection(s) for user %s", len(connections), user.id)
        else:
            connections = await svc.handle_meta_callback(
                code=code, state=state, user=user, db=db,
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
    request: Request,
    user: CurrentUser,
    db: DbSession,
    connection_id: uuid.UUID | None = None,
    _csrf: None = Depends(verify_csrf),
) -> SubmitForApprovalOut:
    """Submit a SocialPost for publish approval.

    ``connection_id`` is optional — when omitted the account's active connection
    for the post's platform is used. The request then appears in the shared
    approval queue, where an admin/owner approves it to publish.
    """
    account_id = _account_id(request)
    req = await svc.submit_for_approval(db, post_id, account_id, user, connection_id=connection_id)
    return SubmitForApprovalOut(
        approval_request_id=req.id,
        message="Post submitted for approval. Approve it in the Approvals queue to publish.",
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
    _verified: AdminUser = Depends(require_verified_email),
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

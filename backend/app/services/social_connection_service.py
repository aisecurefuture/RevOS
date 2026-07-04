"""Social connection service — OAuth flow, token custody, publishing (M5).

Responsibilities:
  - Build Meta OAuth redirect URLs with signed CSRF state
  - Handle OAuth callbacks: exchange code → store tokens in OpenBao → create
    SocialConnection rows in Postgres
  - List/disconnect connections
  - Submit a SocialPost for approval
  - Execute the publish step (called after an ApprovalRequest is approved)
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError, PermissionError_, RevOSError
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.base import utcnow
from app.models.social import SocialPlatform, SocialPost
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.models.user import AdminUser
from app.services import secrets_service
from app.services.social import meta as meta_client

_STATE_SALT = "social-oauth-state"
_STATE_MAX_AGE = 600  # 10 minutes


# ---------------------------------------------------------------------------
# OAuth state helpers
# ---------------------------------------------------------------------------

def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_STATE_SALT)


def make_oauth_state(account_id: uuid.UUID, platform: str) -> str:
    return _signer().dumps({"account_id": str(account_id), "platform": platform})


def verify_oauth_state(state: str) -> dict:
    try:
        return _signer().loads(state, max_age=_STATE_MAX_AGE)
    except SignatureExpired:
        raise RevOSError("OAuth state expired. Please try connecting again.", code="state_expired", status_code=400)
    except BadSignature:
        raise RevOSError("Invalid OAuth state.", code="state_invalid", status_code=400)


# ---------------------------------------------------------------------------
# Token path helpers
# ---------------------------------------------------------------------------

def _token_path(account_id: uuid.UUID, platform: str, connection_id: uuid.UUID) -> str:
    return f"revos/accounts/{account_id}/social/{platform}/{connection_id}"


# ---------------------------------------------------------------------------
# Connect URL
# ---------------------------------------------------------------------------

def get_connect_url(platform: str, account_id: uuid.UUID) -> str:
    if platform not in ("facebook", "instagram"):
        raise RevOSError(f"Platform '{platform}' is not supported in this release.", code="unsupported_platform", status_code=400)
    if not settings.meta_app_id or not settings.meta_app_secret or not settings.meta_redirect_uri:
        raise RevOSError("Meta OAuth is not configured on this server.", code="meta_unconfigured", status_code=503)
    state = make_oauth_state(account_id, platform)
    return meta_client.connect_url(state)


# ---------------------------------------------------------------------------
# Meta OAuth callback
# ---------------------------------------------------------------------------

async def handle_meta_callback(
    *,
    code: str,
    state: str,
    user: AdminUser,
    db: AsyncSession,
) -> list[SocialConnection]:
    """Exchange the authorization code and create SocialConnection rows.

    One connection per Facebook Page + one per linked Instagram Business Account.
    Returns the list of created/updated connections.
    """
    state_data = verify_oauth_state(state)
    account_id = uuid.UUID(state_data["account_id"])

    # Exchange code → short-lived token → long-lived token
    short_token = await meta_client.exchange_code(code)
    tokens = await meta_client.get_long_lived_token(short_token)

    # Discover pages
    pages = await meta_client.get_pages(tokens.user_access_token)
    if not pages:
        raise RevOSError(
            "No Facebook Pages found for this account. "
            "Make sure you manage at least one Page.",
            code="no_pages",
            status_code=400,
        )

    # Get IG accounts for each page
    for page in pages:
        page.ig_account_id = await meta_client.get_ig_account(page.page_id, page.access_token)

    connections: list[SocialConnection] = []

    expires_at = utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None

    for page in pages:
        # Facebook Page connection
        fb_conn = await _upsert_connection(
            db=db,
            account_id=account_id,
            platform=SocialPlatform.facebook,
            external_id=page.page_id,
            handle=None,
            display_name=page.name,
            scopes=meta_client._META_SCOPES.split(","),
            connected_by=user.id,
            expires_at=None,  # page tokens don't expire
            platform_meta={"page_id": page.page_id, "category": page.category},
        )
        # Store page token in OpenBao
        await secrets_service.put_secret(
            _token_path(account_id, "facebook", fb_conn.id),
            {
                "access_token": page.access_token,
                "token_type": "page",
                "page_id": page.page_id,
            },
        )
        fb_conn.token_ref = _token_path(account_id, "facebook", fb_conn.id)
        db.add(fb_conn)
        connections.append(fb_conn)

        # Instagram Business Account connection (if linked)
        if page.ig_account_id:
            ig_conn = await _upsert_connection(
                db=db,
                account_id=account_id,
                platform=SocialPlatform.instagram,
                external_id=page.ig_account_id,
                handle=None,
                display_name=f"{page.name} (Instagram)",
                scopes=meta_client._META_SCOPES.split(","),
                connected_by=user.id,
                expires_at=expires_at,
                platform_meta={"ig_user_id": page.ig_account_id, "page_id": page.page_id},
            )
            await secrets_service.put_secret(
                _token_path(account_id, "instagram", ig_conn.id),
                {
                    "access_token": tokens.user_access_token,
                    "token_type": "instagram_user",
                    "ig_user_id": page.ig_account_id,
                    "page_id": page.page_id,
                },
            )
            ig_conn.token_ref = _token_path(account_id, "instagram", ig_conn.id)
            db.add(ig_conn)
            connections.append(ig_conn)

    await db.flush()
    for conn in connections:
        await db.refresh(conn)
    return connections


async def _upsert_connection(
    *,
    db: AsyncSession,
    account_id: uuid.UUID,
    platform: SocialPlatform,
    external_id: str,
    handle: str | None,
    display_name: str | None,
    scopes: list,
    connected_by: uuid.UUID,
    expires_at,
    platform_meta: dict,
) -> SocialConnection:
    """Update existing connection or create a new one (idempotent)."""
    result = await db.execute(
        select(SocialConnection).where(
            SocialConnection.account_id == account_id,
            SocialConnection.platform == platform,
            SocialConnection.external_id == external_id,
            SocialConnection.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.status = SocialConnectionStatus.active
        existing.handle = handle
        existing.display_name = display_name
        existing.scopes = scopes
        existing.connected_by = connected_by
        existing.expires_at = expires_at
        existing.platform_meta = platform_meta
        db.add(existing)
        return existing

    conn = SocialConnection(
        account_id=account_id,
        platform=platform,
        external_id=external_id,
        handle=handle,
        display_name=display_name,
        scopes=scopes,
        status=SocialConnectionStatus.active,
        token_ref="",  # filled after we know the connection_id
        connected_by=connected_by,
        expires_at=expires_at,
        platform_meta=platform_meta,
    )
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return conn


# ---------------------------------------------------------------------------
# List / get / disconnect
# ---------------------------------------------------------------------------

async def list_connections(db: AsyncSession, account_id: uuid.UUID) -> list[SocialConnection]:
    result = await db.execute(
        select(SocialConnection).where(
            SocialConnection.account_id == account_id,
            SocialConnection.deleted_at.is_(None),
        ).order_by(SocialConnection.created_at.desc())
    )
    return list(result.scalars().all())


async def get_connection(
    db: AsyncSession, connection_id: uuid.UUID, account_id: uuid.UUID
) -> SocialConnection:
    result = await db.execute(
        select(SocialConnection).where(
            SocialConnection.id == connection_id,
            SocialConnection.account_id == account_id,
            SocialConnection.deleted_at.is_(None),
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise NotFoundError("Social connection not found.")
    return conn


async def delete_connections_by_facebook_user_id(
    db: AsyncSession, facebook_user_id: str
) -> int:
    """Delete all social connections whose platform_meta contains the given
    Facebook user ID. Called by the Meta data-deletion callback.

    Returns the number of connections deleted.
    """
    from sqlalchemy import or_
    from app.models.social_connection import SocialPlatform as _SP

    result = await db.execute(
        select(SocialConnection).where(
            SocialConnection.deleted_at.is_(None),
            or_(
                SocialConnection.external_id == facebook_user_id,
                SocialConnection.platform_meta["page_id"].as_string() == facebook_user_id,
            ),
        )
    )
    conns = list(result.scalars().all())
    for conn in conns:
        try:
            if conn.token_ref:
                await secrets_service.delete_secret(conn.token_ref)
        except RevOSError:
            pass
        conn.deleted_at = utcnow()
        conn.status = SocialConnectionStatus.revoked
        db.add(conn)
    if conns:
        await db.flush()
    return len(conns)


async def disconnect(
    db: AsyncSession, connection_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    """Soft-delete the connection and remove its token from OpenBao."""
    conn = await get_connection(db, connection_id, account_id)
    # Remove from Bao (best-effort — don't fail if Bao is unavailable)
    try:
        if conn.token_ref:
            await secrets_service.delete_secret(conn.token_ref)
    except RevOSError:
        pass
    conn.deleted_at = utcnow()
    conn.status = SocialConnectionStatus.revoked
    db.add(conn)
    await db.flush()


# ---------------------------------------------------------------------------
# Approval-first publish
# ---------------------------------------------------------------------------

async def submit_for_approval(
    db: AsyncSession,
    post_id: uuid.UUID,
    connection_id: uuid.UUID,
    account_id: uuid.UUID,
    user: AdminUser,
) -> ApprovalRequest:
    """Create an ApprovalRequest for publishing a SocialPost."""
    # Verify the post belongs to this account
    post_result = await db.execute(
        select(SocialPost).where(
            SocialPost.id == post_id,
            SocialPost.account_id == account_id,
            SocialPost.deleted_at.is_(None),
        )
    )
    post = post_result.scalar_one_or_none()
    if post is None:
        raise NotFoundError("Social post not found.")

    # Verify the connection belongs to this account
    await get_connection(db, connection_id, account_id)

    req = ApprovalRequest(
        account_id=account_id,
        action_type=ApprovalAction.social_publish,
        entity_type="social_post",
        entity_id=post_id,
        title=f"Publish social post to {post.platform}",
        summary=post.caption[:300] if post.caption else None,
        payload={"post_id": str(post_id), "connection_id": str(connection_id)},
        requested_by_user_id=user.id,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req)
    return req


async def execute_publish(
    db: AsyncSession,
    approval_id: uuid.UUID,
    account_id: uuid.UUID,
    user: AdminUser,
) -> SocialPost:
    """Approve and execute the publish for an approval request.

    Owner-only. Marks the request approved and calls the platform adapter.
    """
    from app.models.content import ContentState

    req_result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.account_id == account_id,
        )
    )
    req = req_result.scalar_one_or_none()
    if req is None:
        raise NotFoundError("Approval request not found.")
    if req.status != ApprovalStatus.pending:
        raise RevOSError(f"Request is already {req.status}.", code="not_approvable", status_code=400)

    post_id = uuid.UUID(req.payload["post_id"])
    connection_id = uuid.UUID(req.payload["connection_id"])

    post_result = await db.execute(
        select(SocialPost).where(SocialPost.id == post_id)
    )
    post = post_result.scalar_one_or_none()
    if post is None:
        raise NotFoundError("Social post not found.")

    conn = await get_connection(db, connection_id, account_id)
    token_data = await secrets_service.get_secret(conn.token_ref)
    if token_data is None:
        raise RevOSError("Token not found in secrets store.", code="token_missing", status_code=503)

    # Publish via Meta adapter
    if conn.platform == SocialPlatform.facebook:
        result = await meta_client.publish_to_page(
            page_id=token_data["page_id"],
            page_token=token_data["access_token"],
            caption=post.caption,
        )
    elif conn.platform == SocialPlatform.instagram:
        image_url = post.media_urls[0] if post.media_urls else None
        if not image_url:
            raise RevOSError("Instagram posts require at least one image URL.", code="missing_media", status_code=400)
        result = await meta_client.publish_to_instagram(
            ig_user_id=token_data["ig_user_id"],
            user_token=token_data["access_token"],
            image_url=image_url,
            caption=post.caption,
        )
    else:
        raise RevOSError(f"Platform '{conn.platform}' publishing not yet implemented.", code="unsupported_platform", status_code=400)

    # Update post state
    post.state = ContentState.published
    post.published_at = utcnow()
    post.external_post_id = result.external_id
    post.social_connection_id = connection_id
    db.add(post)

    # Close the approval request
    req.status = ApprovalStatus.approved
    req.reviewed_by_user_id = user.id
    req.reviewed_at = utcnow()
    db.add(req)

    await db.flush()
    await db.refresh(post)
    return post

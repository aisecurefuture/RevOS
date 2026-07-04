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
from datetime import datetime, timedelta

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError, PermissionError_, RevOSError
from app.core.ssrf import validate_outbound_url
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.base import utcnow
from app.models.social import SocialPlatform, SocialPost
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.models.user import AdminUser
from app.services import secrets_service
from app.services.social import meta as meta_client
from app.services.social import threads as threads_client
from app.services.social import x as x_client
from app.services.social import youtube as youtube_client

_STATE_SALT = "social-oauth-state"
_STATE_MAX_AGE = 600  # 10 minutes


# ---------------------------------------------------------------------------
# OAuth state helpers
# ---------------------------------------------------------------------------

def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt=_STATE_SALT)


def make_oauth_state(account_id: uuid.UUID, platform: str, extra: dict | None = None) -> str:
    data = {"account_id": str(account_id), "platform": platform}
    if extra:
        data.update(extra)
    return _signer().dumps(data)


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
    state = make_oauth_state(account_id, platform)
    if platform in ("facebook", "instagram"):
        if not settings.meta_app_id or not settings.meta_app_secret or not settings.meta_redirect_uri:
            raise RevOSError("Meta OAuth is not configured on this server.", code="meta_unconfigured", status_code=503)
        return meta_client.connect_url(state)
    if platform == "threads":
        if not settings.threads_app_id or not settings.threads_app_secret or not settings.threads_redirect_uri:
            raise RevOSError("Threads OAuth is not configured on this server.", code="threads_unconfigured", status_code=503)
        return threads_client.connect_url(state)
    if platform == "youtube":
        if not settings.youtube_client_id or not settings.youtube_client_secret or not settings.youtube_redirect_uri:
            raise RevOSError("YouTube OAuth is not configured on this server.", code="youtube_unconfigured", status_code=503)
        return youtube_client.connect_url(state)
    if platform == "twitter":
        if not settings.twitter_client_id or not settings.twitter_client_secret or not settings.twitter_redirect_uri:
            raise RevOSError("X OAuth is not configured on this server.", code="twitter_unconfigured", status_code=503)
        # PKCE: stash the verifier in the signed state so the callback can
        # complete the exchange without server-side session storage.
        verifier = x_client.generate_code_verifier()
        pkce_state = make_oauth_state(account_id, platform, extra={"cv": verifier})
        return x_client.connect_url(pkce_state, x_client.code_challenge(verifier))
    raise RevOSError(f"Platform '{platform}' is not supported.", code="unsupported_platform", status_code=400)


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


# ---------------------------------------------------------------------------
# Threads OAuth callback
# ---------------------------------------------------------------------------

async def handle_threads_callback(
    *,
    code: str,
    state: str,
    user: AdminUser,
    db: AsyncSession,
) -> list[SocialConnection]:
    """Exchange the Threads authorization code and create a SocialConnection row.

    Unlike Meta (one connection per Page), Threads creates one connection per user.
    Returns a list containing the single created/updated connection.
    """
    state_data = verify_oauth_state(state)
    account_id = uuid.UUID(state_data["account_id"])

    short = await threads_client.exchange_code(code)
    long_lived = await threads_client.get_long_lived_token(short.access_token)
    profile = await threads_client.get_profile(short.user_id, long_lived.access_token)

    expires_at = utcnow() + timedelta(seconds=long_lived.expires_in) if long_lived.expires_in else None

    conn = await _upsert_connection(
        db=db,
        account_id=account_id,
        platform=SocialPlatform.threads,
        external_id=profile.user_id,
        handle=profile.username,
        display_name=profile.name or profile.username,
        scopes=threads_client._THREADS_SCOPES.split(","),
        connected_by=user.id,
        expires_at=expires_at,
        platform_meta={"threads_user_id": profile.user_id},
    )

    token_path = _token_path(account_id, "threads", conn.id)
    await secrets_service.put_secret(
        token_path,
        {
            "access_token": long_lived.access_token,
            "token_type": "threads_user",
            "threads_user_id": profile.user_id,
        },
    )
    conn.token_ref = token_path
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return [conn]


# ---------------------------------------------------------------------------
# YouTube (Google) OAuth callback
# ---------------------------------------------------------------------------

async def handle_youtube_callback(
    *,
    code: str,
    state: str,
    user: AdminUser,
    db: AsyncSession,
) -> list[SocialConnection]:
    """Exchange the Google authorization code and create a channel connection.

    Stores the access token, refresh token, and expiry in OpenBao so publishing
    can refresh the short-lived access token later.
    """
    state_data = verify_oauth_state(state)
    account_id = uuid.UUID(state_data["account_id"])

    tokens = await youtube_client.exchange_code(code)
    if not tokens.refresh_token:
        # Without a refresh token we can't publish once the access token expires
        # (~1h). This happens if the user previously granted consent; prompt=consent
        # in connect_url should prevent it.
        raise RevOSError(
            "Google did not return a refresh token. Remove RevOS from your Google "
            "account permissions and reconnect.",
            code="no_refresh_token",
            status_code=400,
        )
    channel = await youtube_client.get_channel(tokens.access_token)

    expires_at = utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None

    conn = await _upsert_connection(
        db=db,
        account_id=account_id,
        platform=SocialPlatform.youtube,
        external_id=channel.channel_id,
        handle=channel.custom_url,
        display_name=channel.title,
        scopes=youtube_client._SCOPES.split(" "),
        connected_by=user.id,
        expires_at=expires_at,
        platform_meta={"channel_id": channel.channel_id},
    )

    token_path = _token_path(account_id, "youtube", conn.id)
    await secrets_service.put_secret(
        token_path,
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": "youtube_oauth",
            "channel_id": channel.channel_id,
            "expires_at": expires_at.isoformat() if expires_at else "",
        },
    )
    conn.token_ref = token_path
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return [conn]


# ---------------------------------------------------------------------------
# X (Twitter) OAuth callback
# ---------------------------------------------------------------------------

async def handle_x_callback(
    *,
    code: str,
    state: str,
    user: AdminUser,
    db: AsyncSession,
) -> list[SocialConnection]:
    """Complete the X PKCE flow: recover the verifier from state, exchange the
    code, and create the account connection with tokens stored in OpenBao."""
    state_data = verify_oauth_state(state)
    account_id = uuid.UUID(state_data["account_id"])
    code_verifier = state_data.get("cv")
    if not code_verifier:
        raise RevOSError("Missing PKCE verifier in OAuth state.", code="state_invalid", status_code=400)

    tokens = await x_client.exchange_code(code, code_verifier)
    account = await x_client.get_me(tokens.access_token)

    expires_at = utcnow() + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None

    conn = await _upsert_connection(
        db=db,
        account_id=account_id,
        platform=SocialPlatform.twitter,
        external_id=account.user_id,
        handle=account.username,
        display_name=account.name or account.username,
        scopes=x_client._SCOPES.split(" "),
        connected_by=user.id,
        expires_at=expires_at,
        platform_meta={"x_user_id": account.user_id},
    )

    token_path = _token_path(account_id, "twitter", conn.id)
    await secrets_service.put_secret(
        token_path,
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token or "",
            "token_type": "x_oauth",
            "x_user_id": account.user_id,
            "expires_at": expires_at.isoformat() if expires_at else "",
        },
    )
    conn.token_ref = token_path
    db.add(conn)
    await db.flush()
    await db.refresh(conn)
    return [conn]


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
    account_id: uuid.UUID,
    user: AdminUser,
    connection_id: uuid.UUID | None = None,
) -> ApprovalRequest:
    """Create an ApprovalRequest for publishing a SocialPost.

    If ``connection_id`` is omitted, the connection is auto-resolved from the
    post's platform (the account's active connection for that platform). The
    post moves to ``needs_review`` and the request lands in the approval queue.
    """
    from app.models.content import ContentState

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

    if connection_id is not None:
        conn = await get_connection(db, connection_id, account_id)
    else:
        # Auto-resolve: the account's active connection for this platform.
        conn_result = await db.execute(
            select(SocialConnection).where(
                SocialConnection.account_id == account_id,
                SocialConnection.platform == post.platform,
                SocialConnection.status == SocialConnectionStatus.active,
                SocialConnection.deleted_at.is_(None),
            ).order_by(SocialConnection.created_at.desc())
        )
        conn = conn_result.scalars().first()
        if conn is None:
            raise RevOSError(
                f"No connected {post.platform} account. Connect one in "
                f"Settings → Social Connections before submitting for approval.",
                code="no_connection", status_code=400,
            )
        connection_id = conn.id

    req = ApprovalRequest(
        account_id=account_id,
        brand_id=post.brand_id,
        action_type=ApprovalAction.social_publish,
        entity_type="social_post",
        entity_id=post_id,
        title=f"Publish social post to {post.platform}",
        summary=post.caption[:300] if post.caption else None,
        payload={"post_id": str(post_id), "connection_id": str(connection_id)},
        requested_by_user_id=user.id,
    )
    db.add(req)
    # Reflect the pending review on the post so the UI can hide "submit" again.
    post.state = ContentState.needs_review
    post.social_connection_id = connection_id
    db.add(post)
    await db.flush()
    await db.refresh(req)
    return req


async def _youtube_access_token(conn: SocialConnection, token_data: dict) -> str:
    """Return a usable YouTube access token, refreshing + re-storing if expired."""
    expires_at_raw = token_data.get("expires_at") or ""
    still_valid = False
    if expires_at_raw:
        try:
            # Refresh a minute early to avoid racing the edge of expiry.
            still_valid = datetime.fromisoformat(expires_at_raw) > utcnow() + timedelta(seconds=60)
        except ValueError:
            still_valid = False
    if still_valid and token_data.get("access_token"):
        return token_data["access_token"]

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RevOSError(
            "No refresh token stored for this YouTube connection.",
            code="token_missing", status_code=503,
        )
    fresh = await youtube_client.refresh_access_token(refresh_token)
    new_expires = utcnow() + timedelta(seconds=fresh.expires_in) if fresh.expires_in else None
    await secrets_service.put_secret(conn.token_ref, {
        **token_data,
        "access_token": fresh.access_token,
        "expires_at": new_expires.isoformat() if new_expires else "",
    })
    return fresh.access_token


async def _x_access_token(conn: SocialConnection, token_data: dict) -> str:
    """Return a usable X access token, refreshing if expired.

    X rotates refresh tokens on every refresh, so we persist the new
    refresh_token that comes back, not the one we sent.
    """
    expires_at_raw = token_data.get("expires_at") or ""
    still_valid = False
    if expires_at_raw:
        try:
            still_valid = datetime.fromisoformat(expires_at_raw) > utcnow() + timedelta(seconds=60)
        except ValueError:
            still_valid = False
    if still_valid and token_data.get("access_token"):
        return token_data["access_token"]

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RevOSError(
            "No refresh token stored for this X connection. Reconnect the account.",
            code="token_missing", status_code=503,
        )
    fresh = await x_client.refresh_access_token(refresh_token)
    new_expires = utcnow() + timedelta(seconds=fresh.expires_in) if fresh.expires_in else None
    await secrets_service.put_secret(conn.token_ref, {
        **token_data,
        "access_token": fresh.access_token,
        "refresh_token": fresh.refresh_token or refresh_token,
        "expires_at": new_expires.isoformat() if new_expires else "",
    })
    return fresh.access_token


async def _fetch_media_bytes(ref: str) -> bytes:
    """Load media bytes for upload.

    A full http(s) URL (e.g. an external CDN) is fetched over the network with
    SSRF validation and redirects disabled so the allowlist check can't be
    bypassed by a redirect to an internal host. Anything else is treated as a
    storage key and read directly from the configured backend (local disk or
    S3) — so local-storage deployments need no public media host and no SSRF
    allowlist entry.
    """
    if ref.startswith(("http://", "https://")):
        validate_outbound_url(ref)
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=False) as client:
            resp = await client.get(ref)
            if resp.status_code != 200:
                raise RevOSError(
                    f"Could not fetch media for publishing (HTTP {resp.status_code}).",
                    code="media_fetch_failed", status_code=502,
                )
            return resp.content

    # Storage key → read straight from the backend (no network, no SSRF).
    from app.services.storage_service import get_storage
    try:
        return get_storage().read(ref)
    except FileNotFoundError as exc:
        raise RevOSError(
            f"Media '{ref}' was not found in storage.",
            code="media_fetch_failed", status_code=404,
        ) from exc


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
    elif conn.platform == SocialPlatform.youtube:
        video_url = post.media_urls[0] if post.media_urls else None
        if not video_url:
            raise RevOSError("YouTube posts require a video URL in media_urls.", code="missing_media", status_code=400)
        access_token = await _youtube_access_token(conn, token_data)
        video_bytes = await _fetch_media_bytes(video_url)
        title = (post.caption or "Untitled").strip().splitlines()[0][:100] if post.caption else "Untitled"
        result = await youtube_client.upload_video(
            access_token=access_token,
            video_bytes=video_bytes,
            title=title,
            description=post.caption,
        )
    elif conn.platform == SocialPlatform.twitter:
        if not post.caption:
            raise RevOSError("A tweet requires text in the post caption.", code="missing_text", status_code=400)
        access_token = await _x_access_token(conn, token_data)
        result = await x_client.publish_tweet(access_token, post.caption)
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

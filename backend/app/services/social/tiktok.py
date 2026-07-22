"""TikTok (Login Kit + Content Posting API) client — Phase 2 M6.

Standard OAuth 2.0 confidential web flow (no PKCE). Quirks vs the other adapters:
- TikTok names the client id ``client_key`` (not client_id).
- Refresh tokens ROTATE — every refresh returns a new refresh token to persist.
- The token response carries ``open_id``, the user's per-app identifier.
- Publishing is a video Direct Post: init the post (FILE_UPLOAD) to get an
  upload URL, then PUT the bytes. Unaudited apps may only post privately
  (SELF_ONLY) — which suits the approval-first model — until app review clears
  public posting.

Official docs:
  https://developers.tiktok.com/doc/login-kit-web
  https://developers.tiktok.com/doc/content-posting-api-get-started
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.social.tiktok")

_AUTH = "https://www.tiktok.com/v2/auth/authorize/"
_TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
_API = "https://open.tiktokapis.com/v2"
_TIMEOUT = 30.0

_SCOPES = "user.info.basic,video.publish"


@dataclass
class TikTokTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    open_id: str | None


@dataclass
class TikTokUser:
    open_id: str
    display_name: str | None


@dataclass
class PublishResult:
    external_id: str  # publish_id


def connect_url(state: str) -> str:
    """Build the TikTok authorization URL."""
    params = urlencode({
        "client_key": settings.tiktok_client_key,
        "scope": _SCOPES,
        "response_type": "code",
        "redirect_uri": settings.tiktok_redirect_uri,
        "state": state,
    })
    return f"{_AUTH}?{params}"


def _raise_api_error(resp: httpx.Response, context: str) -> None:
    """TikTok wraps failures both in the HTTP status and an ``error`` envelope
    with a ``code`` that is "ok" on success."""
    detail = None
    try:
        body = resp.json()
        err = body.get("error")
        if isinstance(err, dict) and err.get("code") not in (None, "ok"):
            detail = err.get("message") or err.get("code")
    except Exception:
        body = None
    if resp.is_success and detail is None:
        return
    if detail is None:
        detail = resp.text
    logger.warning("TikTok API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"TikTok API error during {context}: {detail}",
        code="tiktok_api_error",
        status_code=502,
    )


async def exchange_code(code: str) -> TikTokTokens:
    """Exchange an authorization code for tokens."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.tiktok_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_api_error(resp, "code_exchange")
        data = resp.json()
        return TikTokTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            open_id=data.get("open_id"),
        )


async def refresh_access_token(refresh_token: str) -> TikTokTokens:
    """Refresh the access token. TikTok rotates the refresh token."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_api_error(resp, "token_refresh")
        data = resp.json()
        return TikTokTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
            open_id=data.get("open_id"),
        )


async def get_user_info(access_token: str) -> TikTokUser:
    """Fetch the authenticated user's basic info."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_API}/user/info/",
            params={"fields": "open_id,display_name"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "get_user_info")
        user = resp.json().get("data", {}).get("user", {})
        if not user.get("open_id"):
            raise RevOSError("TikTok returned no user.", code="no_account", status_code=400)
        return TikTokUser(open_id=user["open_id"], display_name=user.get("display_name"))


async def publish_video(
    access_token: str,
    video_bytes: bytes,
    title: str,
    privacy: str = "SELF_ONLY",
) -> PublishResult:
    """Direct-post a video via FILE_UPLOAD.

    Two steps: init the post (TikTok returns an upload URL), then PUT the bytes
    as a single chunk. Defaults to SELF_ONLY (private) — approval-first, and the
    only level unaudited apps may use.
    """
    size = len(video_bytes)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        init = await client.post(
            f"{_API}/post/publish/video/init/",
            content=json.dumps({
                "post_info": {"title": title[:2200], "privacy_level": privacy},
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,
                    "total_chunk_count": 1,
                },
            }),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )
        _raise_api_error(init, "publish_init")
        data = init.json().get("data", {})
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if not publish_id or not upload_url:
            raise RevOSError(
                "TikTok did not return an upload URL.",
                code="tiktok_api_error", status_code=502,
            )

        put = await client.put(
            upload_url,
            content=video_bytes,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            },
        )
        _raise_api_error(put, "upload_bytes")
        # A successful upload only means TikTok RECEIVED the bytes — publishing
        # is asynchronous. Poll the status endpoint so a downstream FAILED
        # (moderation, format, unaudited-app restriction) surfaces as a real
        # error instead of a false "published". Bounded because this runs
        # inside the synchronous approve request; most failures return fast.
        external_id = await _await_publish(client, access_token, publish_id)
        return PublishResult(external_id=external_id)


async def _await_publish(
    client: httpx.AsyncClient, access_token: str, publish_id: str,
    *, attempts: int = 7, delay: float = 3.0,
) -> str:
    """Poll /post/publish/status/fetch until a terminal state.

    Returns the public post id on completion (falling back to publish_id).
    Raises on FAILED with TikTok's reason. If still processing when the budget
    runs out, returns publish_id optimistically — the upload was accepted and
    TikTok will most likely finish; we just couldn't confirm within the window.
    """
    last_status = None
    for _ in range(attempts):
        resp = await client.post(
            f"{_API}/post/publish/status/fetch/",
            content=json.dumps({"publish_id": publish_id}),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )
        _raise_api_error(resp, "status_fetch")
        data = resp.json().get("data", {})
        last_status = data.get("status")
        if last_status == "PUBLISH_COMPLETE":
            ids = data.get("publicaly_available_post_id") or []
            return str(ids[0]) if ids else publish_id
        if last_status == "FAILED":
            raise RevOSError(
                f"TikTok rejected the video: {data.get('fail_reason') or 'unknown reason'}",
                code="tiktok_publish_failed", status_code=502,
            )
        if last_status == "SEND_TO_USER_INBOX":
            # Delivered to the user's TikTok app inbox to finish manually.
            return publish_id
        await asyncio.sleep(delay)
    logger.warning(
        "TikTok publish %s still %s after %d polls; reporting optimistically",
        publish_id, last_status, attempts,
    )
    return publish_id


# ---------------------------------------------------------------------------
# Audience stats (Phase 6 — live insights ingestion).
# ---------------------------------------------------------------------------
from app.services.social.base import AudienceStats  # noqa: E402


async def get_audience_stats(access_token: str) -> AudienceStats:
    """follower_count from user/info/. TikTok's Login Kit doesn't expose a
    recent-videos endpoint without the additional video.list scope on an
    audited app, so engagement_rate stays None until that's granted."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_API}/user/info/",
            params={"fields": "open_id,follower_count"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "audience_stats")
        user = resp.json().get("data", {}).get("user", {})
        return AudienceStats(follower_count=user.get("follower_count"), engagement_rate=None)

"""Threads OAuth client — Phase 2 M6.

Handles OAuth code exchange, long-lived token upgrade, profile lookup,
and text/image publishing via the Threads Graph API.

Official docs:
  https://developers.facebook.com/docs/threads/get-started
  https://developers.facebook.com/docs/threads/posts
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.social.threads")

_GRAPH = "https://graph.threads.net/v1.0"
_DIALOG = "https://threads.net/oauth/authorize"
_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
_LONG_LIVED_URL = "https://graph.threads.net/access_token"
_TIMEOUT = 15.0

_THREADS_SCOPES = "threads_basic,threads_content_publish"  # default; overridable via THREADS_SCOPES


@dataclass
class ThreadsTokens:
    access_token: str
    user_id: str          # present on short-lived exchange; empty on long-lived refresh
    expires_in: int | None  # seconds until expiry (None = non-expiring)


@dataclass
class ThreadsProfile:
    user_id: str
    username: str | None
    name: str | None


@dataclass
class PublishResult:
    external_id: str


def connect_url(state: str) -> str:
    """Build the Threads OAuth dialog URL."""
    params = urlencode({
        "client_id": settings.threads_app_id,
        "redirect_uri": settings.threads_redirect_uri,
        "scope": settings.threads_scopes or _THREADS_SCOPES,
        "response_type": "code",
        "state": state,
    })
    return f"{_DIALOG}?{params}"


def _raise_graph_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        detail = resp.text
    logger.warning("Threads API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"Threads API error during {context}: {detail}",
        code="threads_api_error",
        status_code=502,
    )


async def exchange_code(code: str) -> ThreadsTokens:
    """Exchange an authorization code for a short-lived access token."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_TOKEN_URL, data={
            "client_id": settings.threads_app_id,
            "client_secret": settings.threads_app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": settings.threads_redirect_uri,
            "code": code,
        })
        _raise_graph_error(resp, "code_exchange")
        data = resp.json()
        return ThreadsTokens(
            access_token=data["access_token"],
            user_id=str(data.get("user_id", "")),
            expires_in=data.get("expires_in"),
        )


async def get_long_lived_token(short_token: str) -> ThreadsTokens:
    """Exchange a short-lived token for a long-lived token (~60 days)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_LONG_LIVED_URL, params={
            "grant_type": "th_exchange_token",
            "client_secret": settings.threads_app_secret,
            "access_token": short_token,
        })
        _raise_graph_error(resp, "long_lived_token")
        data = resp.json()
        return ThreadsTokens(
            access_token=data["access_token"],
            user_id="",
            expires_in=data.get("expires_in"),
        )


async def get_profile(user_id: str, access_token: str) -> ThreadsProfile:
    """Fetch the Threads user profile."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/{user_id}",
            params={
                "fields": "id,username,name",
                "access_token": access_token,
            },
        )
        _raise_graph_error(resp, "get_profile")
        data = resp.json()
        return ThreadsProfile(
            user_id=data["id"],
            username=data.get("username"),
            name=data.get("name"),
        )


async def _wait_until_ready(
    client: httpx.AsyncClient, container_id: str, access_token: str,
    *, attempts: int = 20, delay: float = 2.0,
) -> None:
    """Threads containers process asynchronously. Publishing before the
    container is FINISHED 400s with "The requested resource does not exist",
    so poll status first. Text is ready in a couple seconds; video takes
    longer, hence the generous budget (~40s)."""
    for _ in range(attempts):
        st = await client.get(
            f"{_GRAPH}/{container_id}",
            params={"fields": "status,error_message", "access_token": access_token},
        )
        if st.is_success:
            data = st.json()
            status = data.get("status")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise RevOSError(
                    f"Threads could not process the post: {data.get('error_message') or status}",
                    code="threads_media_failed", status_code=502,
                )
        await asyncio.sleep(delay)
    # Timed out — let the publish attempt surface whatever error remains.


async def _create_and_publish(
    client: httpx.AsyncClient, user_id: str, access_token: str, params: dict,
) -> PublishResult:
    resp = await client.post(f"{_GRAPH}/{user_id}/threads", params=params)
    _raise_graph_error(resp, "create_container")
    container_id = resp.json()["id"]
    await _wait_until_ready(client, container_id, access_token)
    pub = await client.post(
        f"{_GRAPH}/{user_id}/threads_publish",
        params={"creation_id": container_id, "access_token": access_token},
    )
    _raise_graph_error(pub, "publish")
    return PublishResult(external_id=pub.json()["id"])


async def publish_text(user_id: str, access_token: str, text: str) -> PublishResult:
    """Publish a text-only post to Threads (container → wait → publish)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await _create_and_publish(client, user_id, access_token, {
            "media_type": "TEXT", "text": text, "access_token": access_token,
        })


async def publish_media(
    user_id: str, access_token: str, *,
    text: str | None, image_url: str | None = None, video_url: str | None = None,
) -> PublishResult:
    """Publish a single image or video to Threads. Threads FETCHES the media
    from a public URL (same model as Instagram), so callers pass a signed
    public URL, not a storage key. ``text`` becomes the post caption."""
    if video_url:
        params = {"media_type": "VIDEO", "video_url": video_url}
    elif image_url:
        params = {"media_type": "IMAGE", "image_url": image_url}
    else:
        raise RevOSError("A Threads media post needs an image or video.", code="missing_media", status_code=400)
    if text:
        params["text"] = text
    params["access_token"] = access_token
    # Longer per-request timeout: video containers can be slow to accept.
    async with httpx.AsyncClient(timeout=60.0) as client:
        return await _create_and_publish(client, user_id, access_token, params)

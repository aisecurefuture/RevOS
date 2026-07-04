"""Threads OAuth client — Phase 2 M6.

Handles OAuth code exchange, long-lived token upgrade, profile lookup,
and text/image publishing via the Threads Graph API.

Official docs:
  https://developers.facebook.com/docs/threads/get-started
  https://developers.facebook.com/docs/threads/posts
"""

from __future__ import annotations

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

_THREADS_SCOPES = "threads_basic,threads_content_publish"


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
        "scope": _THREADS_SCOPES,
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


async def publish_text(user_id: str, access_token: str, text: str) -> PublishResult:
    """Publish a text-only post to Threads (two-step: container → publish)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Step 1: create container
        resp = await client.post(
            f"{_GRAPH}/{user_id}/threads",
            params={
                "media_type": "TEXT",
                "text": text,
                "access_token": access_token,
            },
        )
        _raise_graph_error(resp, "create_container")
        container_id = resp.json()["id"]

        # Step 2: publish
        resp = await client.post(
            f"{_GRAPH}/{user_id}/threads_publish",
            params={
                "creation_id": container_id,
                "access_token": access_token,
            },
        )
        _raise_graph_error(resp, "publish")
        return PublishResult(external_id=resp.json()["id"])

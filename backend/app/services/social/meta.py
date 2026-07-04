"""Meta (Facebook + Instagram) OAuth client — Phase 2 M5.

Handles the OAuth code exchange, long-lived token upgrade, page/IG account
discovery, and approval-first publishing via the Graph API v21.0.

Official API docs:
  https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow
  https://developers.facebook.com/docs/instagram-api/guides/content-publishing
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.social.meta")

_GRAPH = "https://graph.facebook.com/v21.0"
_DIALOG = "https://www.facebook.com/v21.0/dialog/oauth"
_TIMEOUT = 15.0

# Permissions requested during the OAuth flow.
_META_SCOPES = ",".join([
    "pages_manage_posts",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "business_management",
])


@dataclass
class MetaPage:
    page_id: str
    name: str
    category: str | None
    access_token: str
    ig_account_id: str | None = None


@dataclass
class MetaTokens:
    user_access_token: str
    expires_in: int | None  # seconds; None for non-expiring page tokens


@dataclass
class PublishResult:
    external_id: str
    url: str | None = None


def connect_url(state: str) -> str:
    """Build the Meta OAuth dialog URL."""
    params = (
        f"client_id={settings.meta_app_id}"
        f"&redirect_uri={settings.meta_redirect_uri}"
        f"&state={state}"
        f"&scope={_META_SCOPES}"
        f"&response_type=code"
    )
    return f"{_DIALOG}?{params}"


def _raise_graph_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        detail = resp.text
    logger.warning("Meta Graph API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"Meta API error during {context}: {detail}",
        code="meta_api_error",
        status_code=502,
    )


async def exchange_code(code: str) -> str:
    """Exchange authorization code for a short-lived user access token."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/oauth/access_token",
            params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "redirect_uri": settings.meta_redirect_uri,
                "code": code,
            },
        )
    _raise_graph_error(resp, "code exchange")
    return resp.json()["access_token"]


async def get_long_lived_token(short_token: str) -> MetaTokens:
    """Upgrade a short-lived token to a 60-day long-lived user token."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret,
                "fb_exchange_token": short_token,
            },
        )
    _raise_graph_error(resp, "token upgrade")
    data = resp.json()
    return MetaTokens(
        user_access_token=data["access_token"],
        expires_in=data.get("expires_in"),
    )


async def get_pages(user_token: str) -> list[MetaPage]:
    """Return all Facebook Pages the user manages, with their page access tokens."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/me/accounts",
            params={"access_token": user_token, "fields": "id,name,category,access_token"},
        )
    _raise_graph_error(resp, "listing pages")
    pages = []
    for entry in resp.json().get("data", []):
        pages.append(MetaPage(
            page_id=entry["id"],
            name=entry["name"],
            category=entry.get("category"),
            access_token=entry["access_token"],
        ))
    return pages


async def get_ig_account(page_id: str, page_token: str) -> str | None:
    """Return the Instagram Business Account ID linked to a Facebook Page, or None."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/{page_id}",
            params={
                "fields": "instagram_business_account",
                "access_token": page_token,
            },
        )
    if not resp.is_success:
        return None
    data = resp.json()
    ig = data.get("instagram_business_account")
    return ig["id"] if ig else None


async def publish_to_page(
    page_id: str,
    page_token: str,
    *,
    caption: str | None,
    link: str | None = None,
) -> PublishResult:
    """Post a text/link update to a Facebook Page."""
    payload: dict = {"access_token": page_token}
    if caption:
        payload["message"] = caption
    if link:
        payload["link"] = link
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{_GRAPH}/{page_id}/feed", data=payload)
    _raise_graph_error(resp, "page publish")
    post_id = resp.json()["id"]
    return PublishResult(
        external_id=post_id,
        url=f"https://www.facebook.com/{post_id.replace('_', '/posts/')}",
    )


async def publish_to_instagram(
    ig_user_id: str,
    user_token: str,
    *,
    image_url: str,
    caption: str | None,
) -> PublishResult:
    """Publish a single image to an Instagram Business Account (two-step API)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Step 1 — create media container
        create_resp = await client.post(
            f"{_GRAPH}/{ig_user_id}/media",
            data={
                "image_url": image_url,
                "caption": caption or "",
                "access_token": user_token,
            },
        )
        _raise_graph_error(create_resp, "IG media container")
        container_id = create_resp.json()["id"]

        # Step 2 — publish container
        pub_resp = await client.post(
            f"{_GRAPH}/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": user_token},
        )
    _raise_graph_error(pub_resp, "IG media publish")
    media_id = pub_resp.json()["id"]
    return PublishResult(
        external_id=media_id,
        url=f"https://www.instagram.com/p/{media_id}/",
    )

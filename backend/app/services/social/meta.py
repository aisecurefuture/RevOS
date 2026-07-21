"""Meta (Facebook + Instagram) OAuth client — Phase 2 M5.

Handles the OAuth code exchange, long-lived token upgrade, page/IG account
discovery, and approval-first publishing via the Graph API v21.0.

Official API docs:
  https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow
  https://developers.facebook.com/docs/instagram-api/guides/content-publishing
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urlencode

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
    "pages_manage_engagement",     # read/reply/like/hide comments on Page posts
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",   # read/reply to comments on IG media
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
    """Build the Meta OAuth dialog URL.

    Two flows, chosen by config:
    - Facebook Login for Business (META_LOGIN_CONFIG_ID set): the permissions
      live in the dashboard "configuration", so we pass ``config_id`` and
      NOT ``scope`` — passing raw scopes to a business-login app is what
      triggers Facebook's "Invalid Scopes" screen.
    - Classic Facebook Login (no config id): permissions passed as ``scope``.
    Both use the same code-exchange + Graph endpoints afterward.
    """
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.meta_redirect_uri,
        "state": state,
        "response_type": "code",
    }
    if settings.meta_login_config_id:
        params["config_id"] = settings.meta_login_config_id
    else:
        params["scope"] = _META_SCOPES
    return f"{_DIALOG}?{urlencode(params)}"


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


# Extension Facebook expects for each media content-type. A generic
# octet-stream blob with no extension makes Graph reject the upload as an
# "unsupported format" — the format is inferred from the filename/type.
_EXT_FOR_MIME = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
}


def _upload_part(name: str, data: bytes, content_type: str) -> tuple[str, bytes, str]:
    ext = _EXT_FOR_MIME.get(content_type, "")
    return (f"{name}{ext}", data, content_type)


async def publish_photos_to_page(
    page_id: str,
    page_token: str,
    photos: list[bytes],
    *,
    caption: str | None,
    content_types: list[str] | None = None,
) -> PublishResult:
    """Post one or more photos to a Facebook Page (bytes uploaded directly).

    A single photo publishes straight to /photos. Multiple photos upload
    unpublished first, then attach to a single feed post. ``content_types``
    (one per photo) drives the filename+MIME sent to Graph — default JPEG."""
    def _part(i: int, data: bytes) -> tuple[str, bytes, str]:
        ct = content_types[i] if content_types and i < len(content_types) else "image/jpeg"
        return _upload_part("photo", data, ct)

    async with httpx.AsyncClient(timeout=120.0) as client:
        if len(photos) == 1:
            resp = await client.post(
                f"{_GRAPH}/{page_id}/photos",
                data={"access_token": page_token, "caption": caption or "", "published": "true"},
                files={"source": _part(0, photos[0])},
            )
            _raise_graph_error(resp, "page photo publish")
            pid = resp.json().get("post_id") or resp.json()["id"]
            return PublishResult(external_id=pid, url=f"https://www.facebook.com/{pid.replace('_', '/posts/')}")

        media_fbids: list[str] = []
        for i, data in enumerate(photos):
            up = await client.post(
                f"{_GRAPH}/{page_id}/photos",
                data={"access_token": page_token, "published": "false"},
                files={"source": _part(i, data)},
            )
            _raise_graph_error(up, "page photo upload")
            media_fbids.append(up.json()["id"])
        import json as _json
        feed = await client.post(
            f"{_GRAPH}/{page_id}/feed",
            data={
                "access_token": page_token,
                "message": caption or "",
                "attached_media": _json.dumps([{"media_fbid": i} for i in media_fbids]),
            },
        )
    _raise_graph_error(feed, "page multi-photo publish")
    pid = feed.json()["id"]
    return PublishResult(external_id=pid, url=f"https://www.facebook.com/{pid.replace('_', '/posts/')}")


async def publish_video_to_page(
    page_id: str,
    page_token: str,
    video: bytes,
    *,
    caption: str | None,
    content_type: str = "video/mp4",
) -> PublishResult:
    """Upload a video to a Facebook Page (bytes uploaded directly).

    ``content_type`` sets the filename+MIME sent to Graph. A generic
    octet-stream with no extension is rejected as an "unsupported format"
    even for a valid MP4 — that was the bug this parameter fixes."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{_GRAPH}/{page_id}/videos",
            data={"access_token": page_token, "description": caption or ""},
            files={"source": _upload_part("video", video, content_type)},
        )
    _raise_graph_error(resp, "page video publish")
    vid = resp.json()["id"]
    return PublishResult(external_id=vid, url=f"https://www.facebook.com/{page_id}/videos/{vid}")


async def _ig_publish_container(client: httpx.AsyncClient, ig_user_id: str, user_token: str, container_id: str) -> str:
    pub = await client.post(
        f"{_GRAPH}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": user_token},
    )
    _raise_graph_error(pub, "IG media publish")
    return pub.json()["id"]


async def publish_to_instagram(
    ig_user_id: str,
    user_token: str,
    *,
    image_url: str | None = None,
    image_urls: list[str] | None = None,
    video_url: str | None = None,
    caption: str | None,
) -> PublishResult:
    """Publish to an Instagram Business Account: a single image, a carousel of
    images, or a Reel (video). Media is referenced by PUBLIC URL — Meta fetches
    it, so callers pass signed public links, not storage keys."""
    urls = image_urls or ([image_url] if image_url else [])
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if video_url:
            create = await client.post(
                f"{_GRAPH}/{ig_user_id}/media",
                data={"media_type": "REELS", "video_url": video_url,
                      "caption": caption or "", "access_token": user_token},
            )
            _raise_graph_error(create, "IG reel container")
            container_id = create.json()["id"]
            # Reels process asynchronously — wait for FINISHED before publishing.
            for _ in range(30):
                await asyncio.sleep(4)
                st = await client.get(
                    f"{_GRAPH}/{container_id}",
                    params={"fields": "status_code", "access_token": user_token},
                )
                _raise_graph_error(st, "IG reel status")
                code = st.json().get("status_code")
                if code == "FINISHED":
                    break
                if code == "ERROR":
                    raise RevOSError("Instagram could not process the video.", code="ig_media_failed", status_code=502)
            media_id = await _ig_publish_container(client, ig_user_id, user_token, container_id)

        elif len(urls) > 1:
            child_ids: list[str] = []
            for url in urls[:10]:
                child = await client.post(
                    f"{_GRAPH}/{ig_user_id}/media",
                    data={"image_url": url, "is_carousel_item": "true", "access_token": user_token},
                )
                _raise_graph_error(child, "IG carousel item")
                child_ids.append(child.json()["id"])
            create = await client.post(
                f"{_GRAPH}/{ig_user_id}/media",
                data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
                      "caption": caption or "", "access_token": user_token},
            )
            _raise_graph_error(create, "IG carousel container")
            media_id = await _ig_publish_container(client, ig_user_id, user_token, create.json()["id"])

        else:
            if not urls:
                raise RevOSError("Instagram posts require an image or video.", code="missing_media", status_code=400)
            create = await client.post(
                f"{_GRAPH}/{ig_user_id}/media",
                data={"image_url": urls[0], "caption": caption or "", "access_token": user_token},
            )
            _raise_graph_error(create, "IG media container")
            media_id = await _ig_publish_container(client, ig_user_id, user_token, create.json()["id"])

    return PublishResult(external_id=media_id, url=f"https://www.instagram.com/p/{media_id}/")


# ---------------------------------------------------------------------------
# Comment engagement (Facebook Pages + Instagram) — read / reply / like.
# Requires the pages_manage_engagement + instagram_manage_comments scopes.
# ---------------------------------------------------------------------------

# Shared, platform-neutral comment shape (also used by the YouTube adapter).
from app.services.social.base import IncomingComment  # noqa: E402


async def list_page_comments(page_id: str, page_token: str, *, posts: int = 15, per_post: int = 30) -> list[IncomingComment]:
    """Recent comments across a Facebook Page's recent posts, flattened."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/{page_id}/feed",
            params={
                "fields": f"id,permalink_url,comments.limit({per_post}){{id,message,from,created_time,permalink_url}}",
                "limit": posts,
                "access_token": page_token,
            },
        )
    _raise_graph_error(resp, "page comments")
    out: list[IncomingComment] = []
    for post in resp.json().get("data", []):
        for c in (post.get("comments", {}) or {}).get("data", []):
            frm = c.get("from") or {}
            out.append(IncomingComment(
                post_id=post["id"], comment_id=c["id"], text=c.get("message", "") or "",
                author_name=frm.get("name"), author_id=frm.get("id"),
                permalink=c.get("permalink_url") or post.get("permalink_url"),
                created_time=c.get("created_time"),
            ))
    return out


async def list_ig_comments(ig_user_id: str, token: str, *, media: int = 15, per_media: int = 30) -> list[IncomingComment]:
    """Recent comments across an Instagram Business account's recent media."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_GRAPH}/{ig_user_id}/media",
            params={
                "fields": f"id,permalink,comments.limit({per_media}){{id,text,username,timestamp}}",
                "limit": media,
                "access_token": token,
            },
        )
    _raise_graph_error(resp, "ig comments")
    out: list[IncomingComment] = []
    for m in resp.json().get("data", []):
        for c in (m.get("comments", {}) or {}).get("data", []):
            out.append(IncomingComment(
                post_id=m["id"], comment_id=c["id"], text=c.get("text", "") or "",
                author_name=c.get("username"), author_id=None,
                permalink=m.get("permalink"), created_time=c.get("timestamp"),
            ))
    return out


async def reply_to_page_comment(comment_id: str, page_token: str, message: str) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_GRAPH}/{comment_id}/comments",
            data={"message": message, "access_token": page_token},
        )
    _raise_graph_error(resp, "page comment reply")
    return resp.json()["id"]


async def reply_to_ig_comment(comment_id: str, token: str, message: str) -> str:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_GRAPH}/{comment_id}/replies",
            data={"message": message, "access_token": token},
        )
    _raise_graph_error(resp, "ig comment reply")
    return resp.json()["id"]


async def like_page_comment(comment_id: str, page_token: str) -> None:
    """Like a Facebook Page comment. Instagram has no like-comment API — the
    service treats a like request on an IG comment as unsupported."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_GRAPH}/{comment_id}/likes",
            data={"access_token": page_token},
        )
    _raise_graph_error(resp, "page comment like")

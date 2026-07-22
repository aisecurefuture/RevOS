"""YouTube (Google OAuth 2.0) client — Phase 2 M6.

Handles the Google OAuth code exchange, refresh-token custody, channel
discovery, and resumable video upload.

Unlike Meta page tokens, Google access tokens are short-lived (~1h) and paired
with a long-lived refresh token (granted only with access_type=offline +
prompt=consent). Callers must refresh before publishing when the access token
has expired.

Official docs:
  https://developers.google.com/identity/protocols/oauth2/web-server
  https://developers.google.com/youtube/v3/guides/uploading_a_video
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.social.youtube")

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_API = "https://www.googleapis.com/youtube/v3"
_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
_TIMEOUT = 30.0

_SCOPES = " ".join([
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    # Read comment threads + post replies (comments.insert). Adding this
    # requires reconnecting existing YouTube accounts to re-consent.
    "https://www.googleapis.com/auth/youtube.force-ssl",
])


@dataclass
class YouTubeTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None  # seconds until the access token expires


@dataclass
class YouTubeChannel:
    channel_id: str
    title: str | None
    custom_url: str | None


@dataclass
class PublishResult:
    external_id: str


def connect_url(state: str) -> str:
    """Build the Google OAuth consent URL.

    access_type=offline + prompt=consent forces Google to return a refresh
    token (it only does so on the first consent unless prompt=consent).
    """
    params = urlencode({
        "client_id": settings.youtube_client_id,
        "redirect_uri": settings.youtube_redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })
    return f"{_AUTH}?{params}"


def _raise_api_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("error", {})
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("error_description") or resp.text
    except Exception:
        detail = resp.text
    logger.warning("YouTube API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"YouTube API error during {context}: {detail}",
        code="youtube_api_error",
        status_code=502,
    )


async def exchange_code(code: str) -> YouTubeTokens:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_TOKEN, data={
            "code": code,
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "redirect_uri": settings.youtube_redirect_uri,
            "grant_type": "authorization_code",
        })
        _raise_api_error(resp, "code_exchange")
        data = resp.json()
        return YouTubeTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )


async def refresh_access_token(refresh_token: str) -> YouTubeTokens:
    """Exchange a refresh token for a fresh access token.

    Google does not return a new refresh token here, so the caller keeps the
    existing one.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_TOKEN, data={
            "refresh_token": refresh_token,
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "grant_type": "refresh_token",
        })
        _raise_api_error(resp, "token_refresh")
        data = resp.json()
        return YouTubeTokens(
            access_token=data["access_token"],
            refresh_token=refresh_token,
            expires_in=data.get("expires_in"),
        )


async def get_channel(access_token: str) -> YouTubeChannel:
    """Fetch the authenticated user's primary channel."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_API}/channels",
            params={"part": "id,snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "get_channel")
        items = resp.json().get("items", [])
        if not items:
            raise RevOSError(
                "No YouTube channel found for this Google account.",
                code="no_channel",
                status_code=400,
            )
        ch = items[0]
        snippet = ch.get("snippet", {})
        return YouTubeChannel(
            channel_id=ch["id"],
            title=snippet.get("title"),
            custom_url=snippet.get("customUrl"),
        )


async def upload_video(
    access_token: str,
    video_bytes: bytes,
    title: str,
    description: str | None = None,
    privacy: str = "private",
) -> PublishResult:
    """Upload a video via Google's resumable upload protocol.

    Two steps: (1) POST the metadata to open a resumable session (Google
    returns an upload URL in the Location header); (2) PUT the bytes to it.
    Defaults to privacy="private" — approval-first: the operator flips it to
    public on the platform, or we expose a privacy choice later.
    """
    metadata = {
        "snippet": {"title": title[:100], "description": (description or "")[:5000]},
        "status": {"privacyStatus": privacy},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Step 1: open the resumable session.
        init = await client.post(
            _UPLOAD,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/*",
                "X-Upload-Content-Length": str(len(video_bytes)),
            },
            content=json.dumps(metadata),
        )
        _raise_api_error(init, "upload_init")
        upload_url = init.headers.get("location") or init.headers.get("Location")
        if not upload_url:
            raise RevOSError(
                "YouTube did not return a resumable upload URL.",
                code="youtube_api_error",
                status_code=502,
            )

        # Step 2: upload the bytes.
        put = await client.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "video/*",
                "Content-Length": str(len(video_bytes)),
            },
            content=video_bytes,
        )
        _raise_api_error(put, "upload_bytes")
        return PublishResult(external_id=put.json()["id"])


# ---------------------------------------------------------------------------
# Comment engagement (read + reply). Requires the youtube.force-ssl scope.
# YouTube has no API to "like" a comment, so only read + reply are supported.
# ---------------------------------------------------------------------------

from app.services.social.base import IncomingComment  # noqa: E402


async def list_channel_comments(channel_id: str, access_token: str, *, max_results: int = 50) -> list[IncomingComment]:
    """Top-level comments across all of a channel's videos, newest first."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_API}/commentThreads",
            params={
                "part": "snippet",
                "allThreadsRelatedToChannelId": channel_id,
                "maxResults": min(max_results, 100),
                "order": "time",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
    _raise_api_error(resp, "list_comments")
    out: list[IncomingComment] = []
    for thread in resp.json().get("items", []):
        top = thread.get("snippet", {}).get("topLevelComment", {})
        s = top.get("snippet", {})
        author_channel = s.get("authorChannelId", {}) or {}
        out.append(IncomingComment(
            post_id=thread.get("snippet", {}).get("videoId", ""),
            comment_id=top.get("id", ""),
            text=s.get("textOriginal", "") or "",
            author_name=s.get("authorDisplayName"),
            author_id=author_channel.get("value"),
            permalink=(f"https://www.youtube.com/watch?v={thread['snippet']['videoId']}"
                       if thread.get("snippet", {}).get("videoId") else None),
            created_time=s.get("publishedAt"),
        ))
    return out


async def reply_to_comment(parent_comment_id: str, access_token: str, text: str) -> str:
    """Post a reply to a top-level comment. Returns the new comment id."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_API}/comments",
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            content=json.dumps({"snippet": {"parentId": parent_comment_id, "textOriginal": text}}),
        )
    _raise_api_error(resp, "reply_comment")
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Audience stats (Phase 6 — live insights ingestion).
# ---------------------------------------------------------------------------
from app.services.social.base import AudienceStats  # noqa: E402


async def get_audience_stats(access_token: str) -> AudienceStats:
    """subscriberCount from channels.list; engagement averaged over the last
    ~10 uploaded videos' (likeCount+commentCount)/subscriberCount. Three calls
    (channel → uploads playlist → recent videos), all standard Data API v3."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        chan = await client.get(f"{_API}/channels", params={
            "part": "statistics,contentDetails", "mine": "true"}, headers=headers)
        _raise_api_error(chan, "audience_stats_channel")
        items = chan.json().get("items", [])
        if not items:
            return AudienceStats(follower_count=None, engagement_rate=None)
        stats = items[0].get("statistics", {})
        followers = int(stats["subscriberCount"]) if not stats.get("hiddenSubscriberCount") \
            and stats.get("subscriberCount") is not None else None
        uploads_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not followers or not uploads_id:
            return AudienceStats(follower_count=followers, engagement_rate=None)

        pl = await client.get(f"{_API}/playlistItems", params={
            "part": "contentDetails", "playlistId": uploads_id, "maxResults": 10}, headers=headers)
        if not pl.is_success:
            return AudienceStats(follower_count=followers, engagement_rate=None)
        video_ids = [i["contentDetails"]["videoId"] for i in pl.json().get("items", [])]
        if not video_ids:
            return AudienceStats(follower_count=followers, engagement_rate=None, sample_size=0)

        vids = await client.get(f"{_API}/videos", params={
            "part": "statistics", "id": ",".join(video_ids)}, headers=headers)
        if not vids.is_success:
            return AudienceStats(follower_count=followers, engagement_rate=None)
        video_stats = vids.json().get("items", [])
        total = sum(int(v["statistics"].get("likeCount", 0)) + int(v["statistics"].get("commentCount", 0))
                   for v in video_stats)
        rate = (total / len(video_stats)) / followers if video_stats else None
        return AudienceStats(follower_count=followers, engagement_rate=rate, sample_size=len(video_stats))

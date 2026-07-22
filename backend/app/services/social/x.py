"""X (Twitter) OAuth 2.0 client — Phase 2 M6.

X uses Authorization Code with PKCE. Notes that differ from the other adapters:
- The authorization request carries a code_challenge; the token exchange carries
  the matching code_verifier. We stash the verifier inside our signed OAuth state
  so it round-trips without server-side session storage (safe here because we are
  a confidential client — the token exchange is also protected by the client
  secret via HTTP Basic auth).
- Refresh tokens ROTATE: every refresh returns a brand-new refresh token, so the
  caller must persist whatever comes back (not the token it sent).
- offline.access scope is required to receive a refresh token at all.

Official docs:
  https://developer.x.com/en/docs/authentication/oauth-2-0/authorization-code
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.social.x")

_AUTH = "https://twitter.com/i/oauth2/authorize"
_TOKEN = "https://api.twitter.com/2/oauth2/token"
_API = "https://api.twitter.com/2"
_TIMEOUT = 15.0

_SCOPES = "tweet.read tweet.write users.read offline.access"


@dataclass
class XTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None


@dataclass
class XUser:
    user_id: str
    username: str | None
    name: str | None


@dataclass
class PublishResult:
    external_id: str


def generate_code_verifier() -> str:
    """A high-entropy PKCE verifier (URL-safe, within the 43–128 char range)."""
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    """S256 challenge: base64url(sha256(verifier)) with padding stripped."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def connect_url(state: str, challenge: str) -> str:
    """Build the X OAuth 2.0 authorization URL."""
    params = urlencode({
        "response_type": "code",
        "client_id": settings.twitter_client_id,
        "redirect_uri": settings.twitter_redirect_uri,
        "scope": _SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"{_AUTH}?{params}"


def _raise_api_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        body = resp.json()
        detail = (
            body.get("error_description")
            or body.get("detail")
            or body.get("error")
            or resp.text
        )
    except Exception:
        detail = resp.text
    logger.warning("X API error (%s): HTTP %s — %s", context, resp.status_code, detail)

    # X's monthly write cap surfaces as "credits depleted" / "usage cap
    # exceeded" (often HTTP 429). That's an account plan limit on X's side,
    # not a transient error — give the user an actionable message + code the
    # UI can flag distinctly, rather than a raw passthrough.
    low = (detail or "").lower()
    if (
        "credits depleted" in low
        or "usage cap" in low
        or "usage-cap" in low
        or ("cap" in low and "exceed" in low)
    ):
        raise RevOSError(
            "X (Twitter) has hit the monthly post limit for your X API plan. "
            "This is a limit on your X developer account, not RevOS — check "
            "your plan and usage at developer.x.com, then try again after the "
            "monthly reset or once the plan is upgraded.",
            code="x_usage_cap",
            status_code=402,
        )

    raise RevOSError(
        f"X API error during {context}: {detail}",
        code="x_api_error",
        status_code=502,
    )


def _basic_auth() -> tuple[str, str]:
    """Confidential-client credentials for the token endpoint (HTTP Basic)."""
    return (settings.twitter_client_id, settings.twitter_client_secret)


async def exchange_code(code: str, code_verifier: str) -> XTokens:
    """Exchange an authorization code + PKCE verifier for tokens."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": settings.twitter_client_id,
                "redirect_uri": settings.twitter_redirect_uri,
                "code_verifier": code_verifier,
            },
            auth=_basic_auth(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_api_error(resp, "code_exchange")
        data = resp.json()
        return XTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )


async def refresh_access_token(refresh_token: str) -> XTokens:
    """Refresh the access token. X rotates the refresh token, so the returned
    refresh_token replaces the one we sent."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
                "client_id": settings.twitter_client_id,
            },
            auth=_basic_auth(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_api_error(resp, "token_refresh")
        data = resp.json()
        return XTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
        )


async def get_me(access_token: str) -> XUser:
    """Fetch the authenticated user's account."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_API}/users/me",
            params={"user.fields": "username,name"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "get_me")
        data = resp.json().get("data", {})
        if not data.get("id"):
            raise RevOSError("X returned no account for this token.", code="no_account", status_code=400)
        return XUser(user_id=data["id"], username=data.get("username"), name=data.get("name"))


_UPLOAD = f"{_API}/media/upload"   # v2 chunked media upload (needs media.write scope)
_MEDIA_CHUNK = 4 * 1024 * 1024     # 4 MB — under X's per-APPEND request limit


def _media_id(payload: dict) -> str | None:
    data = payload.get("data") or payload
    return data.get("id") or data.get("media_id_string") or payload.get("media_id_string")


def _processing_info(payload: dict) -> dict | None:
    return (payload.get("data") or payload).get("processing_info")


async def upload_media(
    access_token: str, data: bytes, media_type: str, *, category: str,
) -> str:
    """Chunked-upload one media file, returning its media id for attachment.

    ``category`` is X's media_category: "tweet_image", "tweet_gif", or
    "tweet_video". Video is processed asynchronously — we poll STATUS until
    it succeeds (or fails) before returning.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        init = await client.post(_UPLOAD, headers=headers, data={
            "command": "INIT", "total_bytes": str(len(data)),
            "media_type": media_type, "media_category": category,
        })
        _raise_api_error(init, "media_init")
        media_id = _media_id(init.json())
        if not media_id:
            raise RevOSError("X media upload returned no media id.", code="x_media_error", status_code=502)

        for idx, start in enumerate(range(0, len(data), _MEDIA_CHUNK)):
            chunk = data[start:start + _MEDIA_CHUNK]
            ap = await client.post(
                _UPLOAD, headers=headers,
                data={"command": "APPEND", "media_id": media_id, "segment_index": str(idx)},
                files={"media": ("blob", chunk, "application/octet-stream")},
            )
            _raise_api_error(ap, "media_append")

        fin = await client.post(_UPLOAD, headers=headers, data={"command": "FINALIZE", "media_id": media_id})
        _raise_api_error(fin, "media_finalize")

        info = _processing_info(fin.json())
        while info and info.get("state") in ("pending", "in_progress"):
            await asyncio.sleep(min(int(info.get("check_after_secs", 3)), 10))
            st = await client.get(_UPLOAD, headers=headers, params={"command": "STATUS", "media_id": media_id})
            _raise_api_error(st, "media_status")
            info = _processing_info(st.json())
        if info and info.get("state") == "failed":
            raise RevOSError("X could not process the uploaded media.", code="x_media_failed", status_code=502)
        return str(media_id)


async def publish_tweet(
    access_token: str, text: str | None, *, media_ids: list[str] | None = None,
) -> PublishResult:
    """Post a tweet, optionally with already-uploaded media, on behalf of the user."""
    payload: dict = {}
    if text:
        payload["text"] = text
    if media_ids:
        payload["media"] = {"media_ids": media_ids}
    if not payload:
        raise RevOSError("A tweet needs text or media.", code="empty_tweet", status_code=400)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_API}/tweets",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "publish_tweet")
        return PublishResult(external_id=resp.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Audience stats (Phase 6 — live insights ingestion).
# ---------------------------------------------------------------------------
from app.services.social.base import AudienceStats  # noqa: E402


async def get_audience_stats(access_token: str) -> AudienceStats:
    """followers_count from users/me's public_metrics; engagement averaged
    over the last ~10 tweets' like+retweet+reply counts."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        me = await client.get(f"{_API}/users/me", params={"user.fields": "public_metrics"},
                              headers={"Authorization": f"Bearer {access_token}"})
        _raise_api_error(me, "audience_stats_me")
        data = me.json().get("data", {})
        user_id = data.get("id")
        metrics = data.get("public_metrics", {})
        followers = metrics.get("followers_count")
        if not user_id or not followers:
            return AudienceStats(follower_count=followers, engagement_rate=None)

        tweets = await client.get(f"{_API}/users/{user_id}/tweets", params={
            "tweet.fields": "public_metrics", "max_results": 10, "exclude": "retweets,replies"},
            headers={"Authorization": f"Bearer {access_token}"})
        if not tweets.is_success:
            return AudienceStats(follower_count=followers, engagement_rate=None)
        items = tweets.json().get("data", [])
        if not items:
            return AudienceStats(follower_count=followers, engagement_rate=None, sample_size=0)
        total = sum(
            t.get("public_metrics", {}).get("like_count", 0)
            + t.get("public_metrics", {}).get("retweet_count", 0)
            + t.get("public_metrics", {}).get("reply_count", 0)
            for t in items
        )
        return AudienceStats(follower_count=followers, engagement_rate=(total / len(items)) / followers,
                             sample_size=len(items))

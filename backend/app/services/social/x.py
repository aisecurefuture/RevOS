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


async def publish_tweet(access_token: str, text: str) -> PublishResult:
    """Post a tweet on behalf of the connected user."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_API}/tweets",
            json={"text": text},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "publish_tweet")
        return PublishResult(external_id=resp.json()["data"]["id"])

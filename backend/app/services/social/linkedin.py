"""LinkedIn OAuth 2.0 client — Phase 2 M6.

Standard Authorization Code flow (no PKCE). Identity comes from the OpenID
Connect userinfo endpoint (the "Sign In with LinkedIn using OpenID Connect"
product); publishing uses ugcPosts (the "Share on LinkedIn" product) with the
w_member_social scope.

Notes:
- Access tokens are long-lived (~60 days). Refresh tokens are only issued to
  apps granted that capability; when absent, the connection simply expires and
  the member reconnects. We refresh when a refresh token is present.
- The author of a post is urn:li:person:{member_id}, where member_id is the
  OpenID `sub` claim.

Official docs:
  https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2
  https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.social.linkedin")

_AUTH = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
_API = "https://api.linkedin.com"
_TIMEOUT = 15.0

_SCOPES = "openid profile email w_member_social"


@dataclass
class LinkedInTokens:
    access_token: str
    refresh_token: str | None
    expires_in: int | None


@dataclass
class LinkedInProfile:
    member_id: str          # OpenID `sub` — used to build urn:li:person:{id}
    name: str | None
    email: str | None


@dataclass
class PublishResult:
    external_id: str


def connect_url(state: str) -> str:
    """Build the LinkedIn OAuth authorization URL."""
    params = urlencode({
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": _SCOPES,
        "state": state,
    })
    return f"{_AUTH}?{params}"


def _raise_api_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        body = resp.json()
        detail = (
            body.get("error_description")
            or body.get("message")
            or body.get("error")
            or resp.text
        )
    except Exception:
        detail = resp.text
    logger.warning("LinkedIn API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"LinkedIn API error during {context}: {detail}",
        code="linkedin_api_error",
        status_code=502,
    )


async def exchange_code(code: str) -> LinkedInTokens:
    """Exchange an authorization code for an access token."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.linkedin_redirect_uri,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_api_error(resp, "code_exchange")
        data = resp.json()
        return LinkedInTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
        )


async def refresh_access_token(refresh_token: str) -> LinkedInTokens:
    """Refresh the access token (only for apps granted refresh-token access)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TOKEN,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _raise_api_error(resp, "token_refresh")
        data = resp.json()
        return LinkedInTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
        )


async def get_profile(access_token: str) -> LinkedInProfile:
    """Fetch the member identity from the OpenID Connect userinfo endpoint."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_API}/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_api_error(resp, "get_profile")
        data = resp.json()
        if not data.get("sub"):
            raise RevOSError("LinkedIn returned no member id.", code="no_account", status_code=400)
        return LinkedInProfile(
            member_id=data["sub"],
            name=data.get("name"),
            email=data.get("email"),
        )


_IMAGE_RECIPE = "urn:li:digitalmediaRecipe:feedshare-image"
_VIDEO_RECIPE = "urn:li:digitalmediaRecipe:feedshare-video"


async def register_and_upload(
    access_token: str, member_id: str, data: bytes, *, is_video: bool,
) -> str:
    """Register an upload slot, PUT the bytes, return the asset URN.

    Two-step LinkedIn Vector Asset flow: registerUpload returns a one-time
    upload URL + an asset URN; we PUT the bytes to the URL, then reference the
    URN when creating the share. LinkedIn processes video server-side; the
    share can reference the asset immediately.
    """
    recipe = _VIDEO_RECIPE if is_video else _IMAGE_RECIPE
    register = {
        "registerUploadRequest": {
            "owner": f"urn:li:person:{member_id}",
            "recipes": [recipe],
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        reg = await client.post(
            f"{_API}/v2/assets?action=registerUpload",
            json=register,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            },
        )
        _raise_api_error(reg, "register_upload")
        value = reg.json()["value"]
        asset_urn = value["asset"]
        upload_url = (
            value["uploadMechanism"]
            ["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]
            ["uploadUrl"]
        )
        put = await client.put(
            upload_url,
            content=data,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if put.status_code not in (200, 201):
            _raise_api_error(put, "upload_bytes")
    return asset_urn


async def publish_share(
    access_token: str,
    member_id: str,
    text: str,
    *,
    media: list[str] | None = None,
    media_is_video: bool = False,
) -> PublishResult:
    """Publish a share via ugcPosts, optionally with already-registered media
    asset URNs (``media``)."""
    if media:
        category = "VIDEO" if media_is_video else "IMAGE"
        share_media = [{"status": "READY", "media": urn} for urn in media]
    else:
        category, share_media = "NONE", None

    share_content: dict = {
        "shareCommentary": {"text": text},
        "shareMediaCategory": category,
    }
    if share_media:
        share_content["media"] = share_media

    payload = {
        "author": f"urn:li:person:{member_id}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_API}/v2/ugcPosts",
            json=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            },
        )
        _raise_api_error(resp, "publish_share")
        # The created post URN comes back in the X-RestLi-Id header; fall back
        # to the body id if a future API version moves it there.
        external_id = resp.headers.get("x-restli-id") or resp.json().get("id", "")
        return PublishResult(external_id=external_id)

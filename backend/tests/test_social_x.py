"""Tests for X (Twitter) OAuth 2.0 + PKCE connections — P2-M6.

Network (X API) and OpenBao are mocked. Verifies PKCE challenge derivation,
verifier custody through signed state, refresh-token rotation, and publish.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.core.exceptions import RevOSError
from app.models.social import SocialPlatform
from app.services import social_connection_service as svc
from app.services.social import x as x_client

API = "https://api.twitter.com"
ACCOUNT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    id = USER_ID


# ---------------------------------------------------------------------------
# PKCE primitives
# ---------------------------------------------------------------------------

def test_code_challenge_matches_s256():
    verifier = "abc123_verifier-value"
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert x_client.code_challenge(verifier) == expected
    assert "=" not in x_client.code_challenge(verifier)  # padding stripped


def test_code_verifier_length_in_range():
    v = x_client.generate_code_verifier()
    assert 43 <= len(v) <= 128


# ---------------------------------------------------------------------------
# connect_url + PKCE state custody
# ---------------------------------------------------------------------------

def test_x_connect_url_configured(monkeypatch):
    monkeypatch.setattr(svc.settings, "twitter_client_id", "xid")
    monkeypatch.setattr(svc.settings, "twitter_client_secret", "xsec")
    monkeypatch.setattr(svc.settings, "twitter_redirect_uri", "https://cb.example.com/x")
    url = svc.get_connect_url("twitter", ACCOUNT_ID)
    assert "twitter.com/i/oauth2/authorize" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "state=" in url


def test_x_connect_url_unconfigured(monkeypatch):
    monkeypatch.setattr(svc.settings, "twitter_client_id", "")
    monkeypatch.setattr(svc.settings, "twitter_client_secret", "")
    monkeypatch.setattr(svc.settings, "twitter_redirect_uri", "")
    with pytest.raises(RevOSError) as exc:
        svc.get_connect_url("twitter", ACCOUNT_ID)
    assert exc.value.code == "twitter_unconfigured"


def test_state_carries_pkce_verifier():
    state = svc.make_oauth_state(ACCOUNT_ID, "twitter", extra={"cv": "my-verifier"})
    data = svc.verify_oauth_state(state)
    assert data["cv"] == "my-verifier"
    assert data["platform"] == "twitter"


# ---------------------------------------------------------------------------
# client: token exchange / rotation / me / publish
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exchange_code():
    with respx.mock(base_url=API) as mock:
        mock.post("/2/oauth2/token").mock(return_value=httpx.Response(200, json={
            "access_token": "at-1", "refresh_token": "rt-1", "expires_in": 7200,
        }))
        tokens = await x_client.exchange_code("code", "verifier")
    assert tokens.access_token == "at-1"
    assert tokens.refresh_token == "rt-1"


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token():
    with respx.mock(base_url=API) as mock:
        mock.post("/2/oauth2/token").mock(return_value=httpx.Response(200, json={
            "access_token": "at-2", "refresh_token": "rt-2", "expires_in": 7200,
        }))
        tokens = await x_client.refresh_access_token("rt-1")
    assert tokens.access_token == "at-2"
    assert tokens.refresh_token == "rt-2"  # X issues a NEW refresh token


@pytest.mark.asyncio
async def test_get_me():
    with respx.mock(base_url=API) as mock:
        mock.get("/2/users/me").mock(return_value=httpx.Response(200, json={
            "data": {"id": "u-1", "username": "revos", "name": "RevOS"}
        }))
        me = await x_client.get_me("at-1")
    assert me.user_id == "u-1"
    assert me.username == "revos"


@pytest.mark.asyncio
async def test_publish_tweet():
    with respx.mock(base_url=API) as mock:
        mock.post("/2/tweets").mock(return_value=httpx.Response(201, json={
            "data": {"id": "tweet-99", "text": "hi"}
        }))
        result = await x_client.publish_tweet("at-1", "hi from RevOS")
    assert result.external_id == "tweet-99"


@pytest.mark.asyncio
async def test_publish_tweet_api_error():
    with respx.mock(base_url=API) as mock:
        mock.post("/2/tweets").mock(return_value=httpx.Response(403, json={
            "detail": "not permitted"
        }))
        with pytest.raises(RevOSError) as exc:
            await x_client.publish_tweet("bad", "x")
    assert exc.value.code == "x_api_error"


@pytest.mark.asyncio
async def test_publish_tweet_usage_cap_is_actionable():
    """X's monthly write cap ('credits depleted') gets a distinct, actionable
    error — not a raw passthrough — so the UI can flag it as a plan limit."""
    with respx.mock(base_url=API) as mock:
        mock.post("/2/tweets").mock(return_value=httpx.Response(429, json={
            "title": "UsageCapExceeded", "detail": "Usage cap exceeded: credits depleted.",
        }))
        with pytest.raises(RevOSError) as exc:
            await x_client.publish_tweet("at-1", "hi")
    assert exc.value.code == "x_usage_cap"
    assert exc.value.status_code == 402
    assert "developer.x.com" in exc.value.message


# ---------------------------------------------------------------------------
# handle_x_callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_x_callback_uses_verifier_and_stores_tokens():
    state = svc.make_oauth_state(ACCOUNT_ID, "twitter", extra={"cv": "the-verifier"})
    exchange_mock = AsyncMock(return_value=x_client.XTokens(
        access_token="at-1", refresh_token="rt-1", expires_in=7200,
    ))
    put_secret_mock = AsyncMock()
    with (
        patch.object(x_client, "exchange_code", exchange_mock),
        patch.object(x_client, "get_me", AsyncMock(return_value=x_client.XUser(
            user_id="u-1", username="revos", name="RevOS",
        ))),
        patch("app.services.social_connection_service.secrets_service.put_secret", put_secret_mock),
    ):
        added = []

        class FakeResult:
            def scalar_one_or_none(self):
                return None

        class FakeDB:
            async def execute(self, _stmt):
                return FakeResult()

            def add(self, obj):
                if hasattr(obj, "id") and not obj.id:
                    obj.id = uuid.uuid4()
                added.append(obj)

            async def flush(self):
                for obj in added:
                    if not obj.id:
                        obj.id = uuid.uuid4()

            async def refresh(self, obj):
                pass

        conns = await svc.handle_x_callback(
            code="auth-code", state=state, user=_FakeUser(), db=FakeDB(),
        )

    # The PKCE verifier from the signed state must be handed to the exchange.
    exchange_mock.assert_awaited_once_with("auth-code", "the-verifier")
    assert len(conns) == 1
    assert conns[0].platform == SocialPlatform.twitter
    assert conns[0].handle == "revos"
    stored = put_secret_mock.call_args[0][1]
    assert stored["refresh_token"] == "rt-1"


@pytest.mark.asyncio
async def test_handle_x_callback_missing_verifier_rejected():
    # State without a "cv" (e.g. a Meta-style state) must be refused.
    state = svc.make_oauth_state(ACCOUNT_ID, "twitter")
    with pytest.raises(RevOSError) as exc:
        await svc.handle_x_callback(code="c", state=state, user=_FakeUser(), db=None)
    assert exc.value.code == "state_invalid"


# ---------------------------------------------------------------------------
# refresh helper — token rotation persisted
# ---------------------------------------------------------------------------

class _FakeConn:
    token_ref = "revos/accounts/x/social/twitter/abc"


@pytest.mark.asyncio
async def test_x_access_token_expired_persists_rotated_refresh_token():
    token_data = {"access_token": "stale", "refresh_token": "rt-old",
                  "expires_at": "2000-01-01T00:00:00"}
    put_mock = AsyncMock()
    with (
        patch.object(x_client, "refresh_access_token", AsyncMock(return_value=x_client.XTokens(
            access_token="fresh", refresh_token="rt-new", expires_in=7200,
        ))),
        patch("app.services.social_connection_service.secrets_service.put_secret", put_mock),
    ):
        tok = await svc._x_access_token(_FakeConn(), token_data)
    assert tok == "fresh"
    stored = put_mock.call_args[0][1]
    assert stored["access_token"] == "fresh"
    assert stored["refresh_token"] == "rt-new"  # rotated token persisted, not the old one


@pytest.mark.asyncio
async def test_x_access_token_valid_skips_refresh():
    token_data = {"access_token": "good", "refresh_token": "rt-1",
                  "expires_at": "2999-01-01T00:00:00"}
    refresh_mock = AsyncMock()
    with patch.object(x_client, "refresh_access_token", refresh_mock):
        tok = await svc._x_access_token(_FakeConn(), token_data)
    assert tok == "good"
    refresh_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Media upload (chunked) + attaching media to a tweet
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_media_image_chunked_flow():
    with respx.mock(base_url=API) as mock:
        route = mock.post("/2/media/upload")
        route.side_effect = [
            httpx.Response(200, json={"data": {"id": "media-123"}}),   # INIT
            httpx.Response(200, json={}),                              # APPEND
            httpx.Response(200, json={"data": {"id": "media-123"}}),   # FINALIZE (no processing_info)
        ]
        media_id = await x_client.upload_media("at-1", b"\xff\xd8imgbytes", "image/jpeg", category="tweet_image")
    assert media_id == "media-123"


@pytest.mark.asyncio
async def test_upload_media_video_polls_status_until_done():
    with respx.mock(base_url=API) as mock:
        mock.post("/2/media/upload").side_effect = [
            httpx.Response(200, json={"data": {"id": "vid-9"}}),                                   # INIT
            httpx.Response(200, json={}),                                                          # APPEND
            httpx.Response(200, json={"data": {"id": "vid-9", "processing_info": {"state": "in_progress", "check_after_secs": 0}}}),  # FINALIZE
        ]
        mock.get("/2/media/upload").mock(return_value=httpx.Response(
            200, json={"data": {"processing_info": {"state": "succeeded"}}}))
        media_id = await x_client.upload_media("at-1", b"video", "video/mp4", category="tweet_video")
    assert media_id == "vid-9"


@pytest.mark.asyncio
async def test_publish_tweet_attaches_media_ids():
    captured = {}

    def _capture(request):
        import json as _j
        captured.update(_j.loads(request.content))
        return httpx.Response(201, json={"data": {"id": "tweet-with-media"}})

    with respx.mock(base_url=API) as mock:
        mock.post("/2/tweets").mock(side_effect=_capture)
        result = await x_client.publish_tweet("at-1", "look", media_ids=["media-123"])
    assert result.external_id == "tweet-with-media"
    assert captured["media"]["media_ids"] == ["media-123"]


@pytest.mark.asyncio
async def test_publish_tweet_media_only_no_text():
    with respx.mock(base_url=API) as mock:
        mock.post("/2/tweets").mock(return_value=httpx.Response(201, json={"data": {"id": "t2"}}))
        result = await x_client.publish_tweet("at-1", None, media_ids=["m1"])
    assert result.external_id == "t2"


@pytest.mark.asyncio
async def test_publish_tweet_empty_is_rejected():
    with pytest.raises(RevOSError) as exc:
        await x_client.publish_tweet("at-1", None, media_ids=None)
    assert exc.value.code == "empty_tweet"

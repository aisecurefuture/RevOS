"""Tests for TikTok OAuth connections + video publishing — P2-M6.

Network (TikTok API) and OpenBao are mocked. No real credentials or uploads.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.core.exceptions import RevOSError
from app.models.social import SocialPlatform
from app.services import social_connection_service as svc
from app.services.social import tiktok as tt

AUTH_HOST = "https://www.tiktok.com"
API_HOST = "https://open.tiktokapis.com"
ACCOUNT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    id = USER_ID


# ---------------------------------------------------------------------------
# connect_url gating
# ---------------------------------------------------------------------------

def test_tiktok_connect_url_configured(monkeypatch):
    monkeypatch.setattr(svc.settings, "tiktok_client_key", "ck")
    monkeypatch.setattr(svc.settings, "tiktok_client_secret", "cs")
    monkeypatch.setattr(svc.settings, "tiktok_redirect_uri", "https://cb.example.com/tt")
    url = svc.get_connect_url("tiktok", ACCOUNT_ID)
    assert "tiktok.com/v2/auth/authorize" in url
    assert "client_key=ck" in url
    assert "video.publish" in url
    assert "state=" in url


def test_tiktok_connect_url_unconfigured(monkeypatch):
    monkeypatch.setattr(svc.settings, "tiktok_client_key", "")
    monkeypatch.setattr(svc.settings, "tiktok_client_secret", "")
    monkeypatch.setattr(svc.settings, "tiktok_redirect_uri", "")
    with pytest.raises(RevOSError) as exc:
        svc.get_connect_url("tiktok", ACCOUNT_ID)
    assert exc.value.code == "tiktok_unconfigured"


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exchange_code_returns_open_id():
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/v2/oauth/token/").mock(return_value=httpx.Response(200, json={
            "access_token": "at-1", "refresh_token": "rt-1",
            "expires_in": 86400, "open_id": "open-1",
        }))
        tokens = await tt.exchange_code("code")
    assert tokens.access_token == "at-1"
    assert tokens.open_id == "open-1"


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token():
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/v2/oauth/token/").mock(return_value=httpx.Response(200, json={
            "access_token": "at-2", "refresh_token": "rt-2", "expires_in": 86400,
        }))
        tokens = await tt.refresh_access_token("rt-1")
    assert tokens.access_token == "at-2"
    assert tokens.refresh_token == "rt-2"


@pytest.mark.asyncio
async def test_get_user_info():
    with respx.mock(base_url=API_HOST) as mock:
        mock.get("/v2/user/info/").mock(return_value=httpx.Response(200, json={
            "data": {"user": {"open_id": "open-1", "display_name": "Creator"}},
            "error": {"code": "ok"},
        }))
        u = await tt.get_user_info("at-1")
    assert u.open_id == "open-1"
    assert u.display_name == "Creator"


@pytest.mark.asyncio
async def test_get_user_info_error_envelope():
    """A 200 with a non-ok error envelope must still raise."""
    with respx.mock(base_url=API_HOST) as mock:
        mock.get("/v2/user/info/").mock(return_value=httpx.Response(200, json={
            "data": {}, "error": {"code": "access_token_invalid", "message": "bad token"},
        }))
        with pytest.raises(RevOSError) as exc:
            await tt.get_user_info("bad")
    assert exc.value.code == "tiktok_api_error"


@pytest.mark.asyncio
async def test_publish_video_init_then_upload():
    upload_url = f"{API_HOST}/upload/session/xyz"
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/v2/post/publish/video/init/").mock(return_value=httpx.Response(200, json={
            "data": {"publish_id": "pub-1", "upload_url": upload_url},
            "error": {"code": "ok"},
        }))
        mock.put("/upload/session/xyz").mock(return_value=httpx.Response(201))
        result = await tt.publish_video("at-1", b"video-bytes", title="My clip")
    assert result.external_id == "pub-1"


# ---------------------------------------------------------------------------
# callback + refresh helper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_tiktok_callback():
    state = svc.make_oauth_state(ACCOUNT_ID, "tiktok")
    put_secret_mock = AsyncMock()
    with (
        patch.object(tt, "exchange_code", AsyncMock(return_value=tt.TikTokTokens(
            access_token="at-1", refresh_token="rt-1", expires_in=86400, open_id="open-1",
        ))),
        patch.object(tt, "get_user_info", AsyncMock(return_value=tt.TikTokUser(
            open_id="open-1", display_name="Creator",
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

        conns = await svc.handle_tiktok_callback(
            code="auth-code", state=state, user=_FakeUser(), db=FakeDB(),
        )

    assert len(conns) == 1
    assert conns[0].platform == SocialPlatform.tiktok
    assert conns[0].display_name == "Creator"
    stored = put_secret_mock.call_args[0][1]
    assert stored["open_id"] == "open-1"
    assert stored["refresh_token"] == "rt-1"


class _FakeConn:
    token_ref = "revos/accounts/x/social/tiktok/abc"


@pytest.mark.asyncio
async def test_tiktok_access_token_expired_persists_rotated_token():
    token_data = {"access_token": "stale", "refresh_token": "rt-old", "open_id": "open-1",
                  "expires_at": "2000-01-01T00:00:00"}
    put_mock = AsyncMock()
    with (
        patch.object(tt, "refresh_access_token", AsyncMock(return_value=tt.TikTokTokens(
            access_token="fresh", refresh_token="rt-new", expires_in=86400, open_id="open-1",
        ))),
        patch("app.services.social_connection_service.secrets_service.put_secret", put_mock),
    ):
        tok = await svc._tiktok_access_token(_FakeConn(), token_data)
    assert tok == "fresh"
    assert put_mock.call_args[0][1]["refresh_token"] == "rt-new"

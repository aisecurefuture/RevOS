"""Tests for YouTube (Google OAuth) connections — P2-M6.

Network calls (Google OAuth, YouTube Data API, OpenBao) are mocked with
respx/monkeypatch. No real credentials or uploads.
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
from app.services.social import youtube as yt

TOKEN_HOST = "https://oauth2.googleapis.com"
API_HOST = "https://www.googleapis.com"
ACCOUNT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    id = USER_ID


# ---------------------------------------------------------------------------
# connect_url gating
# ---------------------------------------------------------------------------

def test_youtube_connect_url_configured(monkeypatch):
    monkeypatch.setattr(svc.settings, "youtube_client_id", "gid")
    monkeypatch.setattr(svc.settings, "youtube_client_secret", "gsec")
    monkeypatch.setattr(svc.settings, "youtube_redirect_uri", "https://cb.example.com/yt")
    url = svc.get_connect_url("youtube", ACCOUNT_ID)
    assert "accounts.google.com" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=" in url


def test_youtube_connect_url_unconfigured(monkeypatch):
    monkeypatch.setattr(svc.settings, "youtube_client_id", "")
    monkeypatch.setattr(svc.settings, "youtube_client_secret", "")
    monkeypatch.setattr(svc.settings, "youtube_redirect_uri", "")
    with pytest.raises(RevOSError) as exc:
        svc.get_connect_url("youtube", ACCOUNT_ID)
    assert exc.value.code == "youtube_unconfigured"


# ---------------------------------------------------------------------------
# client: exchange_code / refresh / channel
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exchange_code_returns_refresh_token():
    with respx.mock(base_url=TOKEN_HOST) as mock:
        mock.post("/token").mock(return_value=httpx.Response(200, json={
            "access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3599,
        }))
        tokens = await yt.exchange_code("auth-code")
    assert tokens.access_token == "at-1"
    assert tokens.refresh_token == "rt-1"
    assert tokens.expires_in == 3599


@pytest.mark.asyncio
async def test_refresh_access_token_keeps_refresh_token():
    with respx.mock(base_url=TOKEN_HOST) as mock:
        mock.post("/token").mock(return_value=httpx.Response(200, json={
            "access_token": "at-2", "expires_in": 3599,
        }))
        tokens = await yt.refresh_access_token("rt-1")
    assert tokens.access_token == "at-2"
    assert tokens.refresh_token == "rt-1"  # carried over — Google omits it on refresh


@pytest.mark.asyncio
async def test_get_channel():
    with respx.mock(base_url=API_HOST) as mock:
        mock.get("/youtube/v3/channels").mock(return_value=httpx.Response(200, json={
            "items": [{"id": "chan-1", "snippet": {"title": "My Channel", "customUrl": "@mychan"}}]
        }))
        ch = await yt.get_channel("at-1")
    assert ch.channel_id == "chan-1"
    assert ch.title == "My Channel"
    assert ch.custom_url == "@mychan"


@pytest.mark.asyncio
async def test_get_channel_none_raises():
    with respx.mock(base_url=API_HOST) as mock:
        mock.get("/youtube/v3/channels").mock(return_value=httpx.Response(200, json={"items": []}))
        with pytest.raises(RevOSError) as exc:
            await yt.get_channel("at-1")
    assert exc.value.code == "no_channel"


# ---------------------------------------------------------------------------
# client: resumable upload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_video_resumable():
    location = f"{API_HOST}/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz"
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/upload/youtube/v3/videos").mock(
            return_value=httpx.Response(200, headers={"Location": location})
        )
        mock.put("/upload/youtube/v3/videos").mock(
            return_value=httpx.Response(200, json={"id": "vid-123"})
        )
        result = await yt.upload_video(
            access_token="at-1",
            video_bytes=b"fake-video-bytes",
            title="My Video",
            description="desc",
        )
    assert result.external_id == "vid-123"


@pytest.mark.asyncio
async def test_upload_video_init_error():
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/upload/youtube/v3/videos").mock(
            return_value=httpx.Response(403, json={"error": {"message": "quota exceeded"}})
        )
        with pytest.raises(RevOSError) as exc:
            await yt.upload_video("at-1", b"bytes", title="x")
    assert exc.value.code == "youtube_api_error"


# ---------------------------------------------------------------------------
# handle_youtube_callback (service integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_youtube_callback():
    state = svc.make_oauth_state(ACCOUNT_ID, "youtube")
    put_secret_mock = AsyncMock()
    with (
        patch.object(yt, "exchange_code", AsyncMock(return_value=yt.YouTubeTokens(
            access_token="at-1", refresh_token="rt-1", expires_in=3599,
        ))),
        patch.object(yt, "get_channel", AsyncMock(return_value=yt.YouTubeChannel(
            channel_id="chan-1", title="My Channel", custom_url="@mychan",
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

        conns = await svc.handle_youtube_callback(
            code="auth-code", state=state, user=_FakeUser(), db=FakeDB(),
        )

    assert len(conns) == 1
    assert conns[0].platform == SocialPlatform.youtube
    assert conns[0].display_name == "My Channel"
    # The stored secret must carry the refresh token for later publishing.
    stored = put_secret_mock.call_args[0][1]
    assert stored["refresh_token"] == "rt-1"


@pytest.mark.asyncio
async def test_handle_youtube_callback_no_refresh_token_rejected():
    state = svc.make_oauth_state(ACCOUNT_ID, "youtube")
    with patch.object(yt, "exchange_code", AsyncMock(return_value=yt.YouTubeTokens(
        access_token="at-1", refresh_token=None, expires_in=3599,
    ))):
        with pytest.raises(RevOSError) as exc:
            await svc.handle_youtube_callback(
                code="auth-code", state=state, user=_FakeUser(), db=None,
            )
    assert exc.value.code == "no_refresh_token"


# ---------------------------------------------------------------------------
# token refresh helper
# ---------------------------------------------------------------------------

class _FakeConn:
    token_ref = "revos/accounts/x/social/youtube/abc"


@pytest.mark.asyncio
async def test_fetch_media_bytes_local_key_reads_from_storage():
    """A storage key (not an http URL) is read straight from the backend —
    no network fetch, no SSRF allowlist needed. This is the local-storage path."""
    class FakeStorage:
        def read(self, key):
            assert key == "media/abc/original/clip.mp4"
            return b"disk-bytes"

    with patch("app.services.storage_service.get_storage", lambda: FakeStorage()):
        data = await svc._fetch_media_bytes("media/abc/original/clip.mp4")
    assert data == b"disk-bytes"


@pytest.mark.asyncio
async def test_fetch_media_bytes_missing_local_key_404():
    class FakeStorage:
        def read(self, key):
            raise FileNotFoundError(key)

    with patch("app.services.storage_service.get_storage", lambda: FakeStorage()):
        with pytest.raises(RevOSError) as exc:
            await svc._fetch_media_bytes("media/missing.mp4")
    assert exc.value.code == "media_fetch_failed"


@pytest.mark.asyncio
async def test_youtube_access_token_valid_skips_refresh():
    token_data = {"access_token": "still-good", "refresh_token": "rt-1",
                  "expires_at": "2999-01-01T00:00:00"}
    refresh_mock = AsyncMock()
    with patch.object(yt, "refresh_access_token", refresh_mock):
        tok = await svc._youtube_access_token(_FakeConn(), token_data)
    assert tok == "still-good"
    refresh_mock.assert_not_called()


@pytest.mark.asyncio
async def test_youtube_access_token_expired_refreshes_and_restores():
    token_data = {"access_token": "stale", "refresh_token": "rt-1",
                  "expires_at": "2000-01-01T00:00:00"}
    put_mock = AsyncMock()
    with (
        patch.object(yt, "refresh_access_token", AsyncMock(return_value=yt.YouTubeTokens(
            access_token="fresh", refresh_token="rt-1", expires_in=3599,
        ))),
        patch("app.services.social_connection_service.secrets_service.put_secret", put_mock),
    ):
        tok = await svc._youtube_access_token(_FakeConn(), token_data)
    assert tok == "fresh"
    # The refreshed token must be written back to the vault.
    assert put_mock.called
    assert put_mock.call_args[0][1]["access_token"] == "fresh"

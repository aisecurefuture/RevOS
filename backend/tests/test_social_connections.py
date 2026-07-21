"""Tests for social connections + Meta OAuth (P2-M5).

Network calls (Meta Graph API, OpenBao) are fully mocked with respx/monkeypatch.
Database uses the in-memory SQLite conftest fixture.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from app.models.social import SocialPlatform
from app.models.social_connection import SocialConnectionStatus
from app.services import social_connection_service as svc
from app.services.social import meta as meta_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GRAPH = "https://graph.facebook.com/v21.0"
ACCOUNT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    id = USER_ID


# ---------------------------------------------------------------------------
# OAuth state signing
# ---------------------------------------------------------------------------

def test_make_and_verify_state():
    state = svc.make_oauth_state(ACCOUNT_ID, "facebook")
    data = svc.verify_oauth_state(state)
    assert data["account_id"] == str(ACCOUNT_ID)
    assert data["platform"] == "facebook"


def test_state_carries_user_id_for_cookieless_callback():
    """The callback runs on a different subdomain than the session cookie, so
    the connecting user must travel in the signed state, not the cookie."""
    state = svc.make_oauth_state(ACCOUNT_ID, "twitter", USER_ID)
    data = svc.verify_oauth_state(state)
    assert data["user_id"] == str(USER_ID)


@pytest.mark.asyncio
async def test_resolve_state_user_prefers_state_then_owner(api, async_session_factory):
    """resolve_state_user identifies the connector from the signed state
    without any session cookie; it falls back to the account owner for older
    states minted before user_id was signed in."""
    r = await api.post("/api/auth/register", json={
        "email": "owner@test.com", "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    me = (await api.get("/api/auth/me", headers={"X-CSRF-Token": r.json()["csrf_token"]})).json()
    user_id = uuid.UUID(me["id"])

    from app.models.account import Account
    from sqlalchemy import select

    async with async_session_factory() as s:
        account = (await s.execute(select(Account))).scalars().first()
        # State WITH user_id → returns exactly that user.
        u = await svc.resolve_state_user(s, {"account_id": str(account.id), "user_id": str(user_id)})
        assert u.id == user_id
        # State WITHOUT user_id → falls back to the account owner.
        u2 = await svc.resolve_state_user(s, {"account_id": str(account.id)})
        assert u2.id == account.owner_user_id


def test_verify_state_invalid():
    from app.core.exceptions import RevOSError
    with pytest.raises(RevOSError) as exc_info:
        svc.verify_oauth_state("not-a-valid-token")
    assert exc_info.value.code == "state_invalid"


# ---------------------------------------------------------------------------
# connect_url
# ---------------------------------------------------------------------------

def test_get_connect_url(monkeypatch):
    monkeypatch.setattr(svc.settings, "meta_app_id", "app123")
    monkeypatch.setattr(svc.settings, "meta_app_secret", "sec")
    monkeypatch.setattr(svc.settings, "meta_redirect_uri", "https://example.com/callback")

    monkeypatch.setattr(svc.settings, "meta_login_config_id", "")
    url = svc.get_connect_url("facebook", ACCOUNT_ID)
    assert "www.facebook.com" in url
    assert "app123" in url
    assert "state=" in url
    # Classic flow: permissions passed as scope.
    assert "scope=" in url
    assert "config_id=" not in url


def test_get_connect_url_business_login_uses_config_id(monkeypatch):
    """Facebook Login for Business: pass config_id, NOT scope (raw scopes on a
    business-login app trigger Facebook's 'Invalid Scopes' error)."""
    monkeypatch.setattr(svc.settings, "meta_app_id", "app123")
    monkeypatch.setattr(svc.settings, "meta_app_secret", "sec")
    monkeypatch.setattr(svc.settings, "meta_redirect_uri", "https://example.com/callback")
    monkeypatch.setattr(svc.settings, "meta_login_config_id", "cfg-999")

    url = svc.get_connect_url("facebook", ACCOUNT_ID)
    assert "config_id=cfg-999" in url
    assert "scope=" not in url


def test_get_connect_url_unsupported_platform():
    from app.core.exceptions import RevOSError
    with pytest.raises(RevOSError) as exc_info:
        svc.get_connect_url("pinterest", ACCOUNT_ID)
    assert exc_info.value.code == "unsupported_platform"


def test_get_connect_url_unconfigured(monkeypatch):
    from app.core.exceptions import RevOSError
    monkeypatch.setattr(svc.settings, "meta_app_id", "")
    monkeypatch.setattr(svc.settings, "meta_app_secret", "")
    monkeypatch.setattr(svc.settings, "meta_redirect_uri", "")
    with pytest.raises(RevOSError) as exc_info:
        svc.get_connect_url("facebook", ACCOUNT_ID)
    assert exc_info.value.code == "meta_unconfigured"


# ---------------------------------------------------------------------------
# Meta client — exchange_code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exchange_code(monkeypatch):
    monkeypatch.setattr(meta_client.settings, "meta_app_id", "app123")
    monkeypatch.setattr(meta_client.settings, "meta_app_secret", "sec")
    monkeypatch.setattr(meta_client.settings, "meta_redirect_uri", "https://cb.example.com")

    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "short-token"})
        )
        token = await meta_client.exchange_code("auth-code")

    assert token == "short-token"


@pytest.mark.asyncio
async def test_get_long_lived_token(monkeypatch):
    monkeypatch.setattr(meta_client.settings, "meta_app_id", "app123")
    monkeypatch.setattr(meta_client.settings, "meta_app_secret", "sec")

    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/oauth/access_token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "long-token", "expires_in": 5184000}
            )
        )
        result = await meta_client.get_long_lived_token("short-token")

    assert result.user_access_token == "long-token"
    assert result.expires_in == 5184000


@pytest.mark.asyncio
async def test_get_pages(monkeypatch):
    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/me/accounts").mock(
            return_value=httpx.Response(200, json={
                "data": [
                    {"id": "page-1", "name": "My Page", "category": "Software", "access_token": "page-tok"},
                ]
            })
        )
        pages = await meta_client.get_pages("user-token")

    assert len(pages) == 1
    assert pages[0].page_id == "page-1"
    assert pages[0].access_token == "page-tok"


@pytest.mark.asyncio
async def test_get_ig_account_present(monkeypatch):
    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/page-1").mock(
            return_value=httpx.Response(200, json={
                "instagram_business_account": {"id": "ig-999"},
                "id": "page-1",
            })
        )
        ig_id = await meta_client.get_ig_account("page-1", "page-tok")

    assert ig_id == "ig-999"


@pytest.mark.asyncio
async def test_get_ig_account_absent(monkeypatch):
    with respx.mock(base_url=GRAPH) as mock:
        mock.get("/page-1").mock(
            return_value=httpx.Response(200, json={"id": "page-1"})
        )
        ig_id = await meta_client.get_ig_account("page-1", "page-tok")

    assert ig_id is None


# ---------------------------------------------------------------------------
# handle_meta_callback (service integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_meta_callback(monkeypatch):
    """Full callback: code exchange + page discovery + Bao write + DB rows."""
    monkeypatch.setattr(svc.settings, "meta_app_id", "app123")
    monkeypatch.setattr(svc.settings, "meta_app_secret", "sec")
    monkeypatch.setattr(svc.settings, "meta_redirect_uri", "https://cb.example.com")

    state = svc.make_oauth_state(ACCOUNT_ID, "facebook")

    # Mock the three Meta API steps
    put_secret_mock = AsyncMock()
    with (
        patch.object(meta_client, "exchange_code", AsyncMock(return_value="short-tok")),
        patch.object(meta_client, "get_long_lived_token", AsyncMock(
            return_value=meta_client.MetaTokens(user_access_token="long-tok", expires_in=5184000)
        )),
        patch.object(meta_client, "get_pages", AsyncMock(return_value=[
            meta_client.MetaPage(
                page_id="pg-1", name="Test Page", category="Tech", access_token="page-tok"
            )
        ])),
        patch.object(meta_client, "get_ig_account", AsyncMock(return_value=None)),
        patch("app.services.social_connection_service.secrets_service.put_secret", put_secret_mock),
    ):
        # Use a minimal fake DB that records added objects
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

        conns = await svc.handle_meta_callback(
            code="auth-code",
            state=state,
            user=_FakeUser(),
            db=FakeDB(),
        )

    assert len(conns) == 1
    fb_conn = conns[0]
    assert fb_conn.platform == SocialPlatform.facebook
    assert fb_conn.display_name == "Test Page"
    assert put_secret_mock.called


# ---------------------------------------------------------------------------
# publish_to_page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_to_page():
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/pg-1/feed").mock(
            return_value=httpx.Response(200, json={"id": "pg-1_12345"})
        )
        result = await meta_client.publish_to_page(
            page_id="pg-1",
            page_token="tok",
            caption="Hello from RevOS!",
        )

    assert result.external_id == "pg-1_12345"


@pytest.mark.asyncio
async def test_publish_to_page_api_error():
    from app.core.exceptions import RevOSError
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/pg-1/feed").mock(
            return_value=httpx.Response(400, json={"error": {"message": "Invalid token"}})
        )
        with pytest.raises(RevOSError) as exc_info:
            await meta_client.publish_to_page("pg-1", "bad-tok", caption="test")

    assert exc_info.value.code == "meta_api_error"


# ---------------------------------------------------------------------------
# publish_to_instagram
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_to_instagram():
    with respx.mock(base_url=GRAPH) as mock:
        mock.post("/ig-1/media").mock(
            return_value=httpx.Response(200, json={"id": "container-99"})
        )
        mock.post("/ig-1/media_publish").mock(
            return_value=httpx.Response(200, json={"id": "media-555"})
        )
        result = await meta_client.publish_to_instagram(
            ig_user_id="ig-1",
            user_token="tok",
            image_url="https://cdn.example.com/img.jpg",
            caption="Hello IG!",
        )

    assert result.external_id == "media-555"


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disconnect_calls_bao_delete(monkeypatch):
    from app.models.social_connection import SocialConnection

    conn = SocialConnection(
        id=uuid.uuid4(),
        account_id=ACCOUNT_ID,
        platform=SocialPlatform.facebook,
        external_id="pg-1",
        status=SocialConnectionStatus.active,
        token_ref="revos/accounts/x/social/facebook/abc",
        connected_by=USER_ID,
    )

    delete_mock = AsyncMock()

    class FakeResult:
        def scalar_one_or_none(self):
            return conn

    class FakeDB:
        async def execute(self, _stmt):
            return FakeResult()

        def add(self, obj):
            pass

        async def flush(self):
            pass

    with patch("app.services.social_connection_service.secrets_service.delete_secret", delete_mock):
        await svc.disconnect(FakeDB(), conn.id, ACCOUNT_ID)

    delete_mock.assert_called_once_with("revos/accounts/x/social/facebook/abc")
    assert conn.status == SocialConnectionStatus.revoked


@pytest.mark.asyncio
async def test_dispatch_selects_video_ref_for_tiktok_and_youtube():
    """TikTok/YouTube pick the video from mixed media and give a clear error
    when only images are attached (the Phase-3 hardening)."""
    from app.core.exceptions import RevOSError
    from app.models.social import SocialPlatform, SocialPost
    from app.models.social_connection import SocialConnection
    from app.services import social_connection_service as svc

    # Only-images → clear missing-media error (no network).
    for platform in (SocialPlatform.tiktok, SocialPlatform.youtube):
        post = SocialPost(brand_id=uuid.uuid4(), platform=platform,
                          caption="hi", media_urls=["media/a/original/x.jpg"])
        conn = SocialConnection(account_id=ACCOUNT_ID, platform=platform, handle="h")
        with pytest.raises(RevOSError) as exc:
            await svc._dispatch_publish(post, conn, {"access_token": "t"})
        assert exc.value.code == "missing_media"
        assert "video" in exc.value.message.lower()

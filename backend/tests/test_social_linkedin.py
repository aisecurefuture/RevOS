"""Tests for LinkedIn OAuth connections — P2-M6.

Network (LinkedIn API) and OpenBao are mocked. No real credentials.
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
from app.services.social import linkedin as li

AUTH_HOST = "https://www.linkedin.com"
API_HOST = "https://api.linkedin.com"
ACCOUNT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    id = USER_ID


# ---------------------------------------------------------------------------
# connect_url gating
# ---------------------------------------------------------------------------

def test_linkedin_connect_url_configured(monkeypatch):
    monkeypatch.setattr(svc.settings, "linkedin_client_id", "lid")
    monkeypatch.setattr(svc.settings, "linkedin_client_secret", "lsec")
    monkeypatch.setattr(svc.settings, "linkedin_redirect_uri", "https://cb.example.com/li")
    url = svc.get_connect_url("linkedin", ACCOUNT_ID)
    assert "linkedin.com/oauth/v2/authorization" in url
    assert "w_member_social" in url
    assert "state=" in url


def test_linkedin_connect_url_unconfigured(monkeypatch):
    monkeypatch.setattr(svc.settings, "linkedin_client_id", "")
    monkeypatch.setattr(svc.settings, "linkedin_client_secret", "")
    monkeypatch.setattr(svc.settings, "linkedin_redirect_uri", "")
    with pytest.raises(RevOSError) as exc:
        svc.get_connect_url("linkedin", ACCOUNT_ID)
    assert exc.value.code == "linkedin_unconfigured"


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exchange_code():
    with respx.mock(base_url=AUTH_HOST) as mock:
        mock.post("/oauth/v2/accessToken").mock(return_value=httpx.Response(200, json={
            "access_token": "at-1", "expires_in": 5184000,
        }))
        tokens = await li.exchange_code("code")
    assert tokens.access_token == "at-1"
    assert tokens.expires_in == 5184000


@pytest.mark.asyncio
async def test_get_profile():
    with respx.mock(base_url=API_HOST) as mock:
        mock.get("/v2/userinfo").mock(return_value=httpx.Response(200, json={
            "sub": "member-1", "name": "Pat Kelly", "email": "pat@example.com",
        }))
        p = await li.get_profile("at-1")
    assert p.member_id == "member-1"
    assert p.name == "Pat Kelly"


@pytest.mark.asyncio
async def test_publish_share_reads_restli_id_header():
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/v2/ugcPosts").mock(return_value=httpx.Response(
            201, headers={"X-RestLi-Id": "urn:li:share:12345"}, json={},
        ))
        result = await li.publish_share("at-1", "member-1", "Hello LinkedIn")
    assert result.external_id == "urn:li:share:12345"


@pytest.mark.asyncio
async def test_publish_share_api_error():
    with respx.mock(base_url=API_HOST) as mock:
        mock.post("/v2/ugcPosts").mock(return_value=httpx.Response(
            403, json={"message": "not permitted"},
        ))
        with pytest.raises(RevOSError) as exc:
            await li.publish_share("bad", "member-1", "x")
    assert exc.value.code == "linkedin_api_error"


# ---------------------------------------------------------------------------
# handle_linkedin_callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_linkedin_callback():
    state = svc.make_oauth_state(ACCOUNT_ID, "linkedin")
    put_secret_mock = AsyncMock()
    with (
        patch.object(li, "exchange_code", AsyncMock(return_value=li.LinkedInTokens(
            access_token="at-1", refresh_token=None, expires_in=5184000,
        ))),
        patch.object(li, "get_profile", AsyncMock(return_value=li.LinkedInProfile(
            member_id="member-1", name="Pat Kelly", email="pat@example.com",
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

        conns = await svc.handle_linkedin_callback(
            code="auth-code", state=state, user=_FakeUser(), db=FakeDB(),
        )

    assert len(conns) == 1
    assert conns[0].platform == SocialPlatform.linkedin
    assert conns[0].display_name == "Pat Kelly"
    stored = put_secret_mock.call_args[0][1]
    assert stored["member_id"] == "member-1"


# ---------------------------------------------------------------------------
# access-token helper
# ---------------------------------------------------------------------------

class _FakeConn:
    token_ref = "revos/accounts/x/social/linkedin/abc"


@pytest.mark.asyncio
async def test_linkedin_access_token_valid_no_refresh():
    token_data = {"access_token": "good", "member_id": "m-1", "expires_at": "2999-01-01T00:00:00"}
    refresh_mock = AsyncMock()
    with patch.object(li, "refresh_access_token", refresh_mock):
        tok = await svc._linkedin_access_token(_FakeConn(), token_data)
    assert tok == "good"
    refresh_mock.assert_not_called()


@pytest.mark.asyncio
async def test_linkedin_access_token_expired_no_refresh_token_asks_reconnect():
    token_data = {"access_token": "stale", "member_id": "m-1",
                  "refresh_token": "", "expires_at": "2000-01-01T00:00:00"}
    with pytest.raises(RevOSError) as exc:
        await svc._linkedin_access_token(_FakeConn(), token_data)
    assert exc.value.code == "token_expired"

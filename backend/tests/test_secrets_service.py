"""Tests for app.services.secrets_service (OpenBao KV v2).

All network calls are intercepted with respx so no real OpenBao instance is
needed.  Settings overrides are applied via monkeypatch to keep tests
hermetic and independent.
"""

from __future__ import annotations

import pytest
import respx
import httpx

from app.core.exceptions import RevOSError
from app.services import secrets_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BAO_ADDR = "http://openbao:8200"
MOUNT = "secret"


def _data_url(path: str) -> str:
    return f"{BAO_ADDR}/v1/{MOUNT}/data/{path}"


def _meta_url(path: str) -> str:
    return f"{BAO_ADDR}/v1/{MOUNT}/metadata/{path}"


# ---------------------------------------------------------------------------
# put_secret / get_secret
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_and_get_secret(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_token", "root-token")
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)
    monkeypatch.setattr(secrets_service.settings, "bao_kv_mount", MOUNT)

    path = "revos/accounts/abc123/social/meta"
    payload = {"access_token": "tok", "refresh_token": "ref", "expires_at": 9999}

    with respx.mock(base_url=BAO_ADDR) as mock:
        put_route = mock.post(f"/v1/{MOUNT}/data/{path}").mock(
            return_value=httpx.Response(200, json={"data": {"version": 1}})
        )
        get_route = mock.get(f"/v1/{MOUNT}/data/{path}").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"data": payload, "metadata": {"version": 1}}},
            )
        )

        await secrets_service.put_secret(path, payload)
        result = await secrets_service.get_secret(path)

    assert put_route.called
    # Verify the PUT body contained {"data": payload}
    put_body = put_route.calls[0].request.read()
    import json
    assert json.loads(put_body) == {"data": payload}

    assert result == payload
    assert get_route.called


# ---------------------------------------------------------------------------
# get_secret — 404 → None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_secret_not_found(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_token", "root-token")
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)
    monkeypatch.setattr(secrets_service.settings, "bao_kv_mount", MOUNT)

    path = "revos/accounts/missing/social/meta"

    with respx.mock(base_url=BAO_ADDR) as mock:
        mock.get(f"/v1/{MOUNT}/data/{path}").mock(
            return_value=httpx.Response(404, json={"errors": []})
        )
        result = await secrets_service.get_secret(path)

    assert result is None


# ---------------------------------------------------------------------------
# delete_secret
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_secret(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_token", "root-token")
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)
    monkeypatch.setattr(secrets_service.settings, "bao_kv_mount", MOUNT)

    path = "revos/accounts/abc123/social/linkedin"

    with respx.mock(base_url=BAO_ADDR) as mock:
        del_route = mock.delete(f"/v1/{MOUNT}/metadata/{path}").mock(
            return_value=httpx.Response(204)
        )
        await secrets_service.delete_secret(path)

    assert del_route.called


# ---------------------------------------------------------------------------
# list_secrets
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_secrets(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_token", "root-token")
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)
    monkeypatch.setattr(secrets_service.settings, "bao_kv_mount", MOUNT)

    path = "revos/accounts/abc123/social"
    expected_keys = ["meta", "linkedin", "twitter"]

    with respx.mock(base_url=BAO_ADDR) as mock:
        mock.request("LIST", f"/v1/{MOUNT}/metadata/{path}").mock(
            return_value=httpx.Response(
                200, json={"data": {"keys": expected_keys}}
            )
        )
        result = await secrets_service.list_secrets(path)

    assert result == expected_keys


# ---------------------------------------------------------------------------
# put_secret raises when bao_token is empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_put_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_token", "")

    with pytest.raises(RevOSError) as exc_info:
        await secrets_service.put_secret("some/path", {"key": "value"})

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "bao_unavailable"


# ---------------------------------------------------------------------------
# is_healthy — sealed=false → True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_healthy_true(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)

    with respx.mock(base_url=BAO_ADDR) as mock:
        mock.get("/v1/sys/health").mock(
            return_value=httpx.Response(
                200,
                json={"initialized": True, "sealed": False, "standby": False},
            )
        )
        result = await secrets_service.is_healthy()

    assert result is True


# ---------------------------------------------------------------------------
# is_healthy — sealed=true → False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_healthy_false_when_sealed(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)

    with respx.mock(base_url=BAO_ADDR) as mock:
        mock.get("/v1/sys/health").mock(
            return_value=httpx.Response(
                503,
                json={"initialized": True, "sealed": True, "standby": False},
            )
        )
        result = await secrets_service.is_healthy()

    assert result is False


# ---------------------------------------------------------------------------
# is_healthy — connection error → False
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_is_healthy_false_on_error(monkeypatch):
    monkeypatch.setattr(secrets_service.settings, "bao_addr", BAO_ADDR)

    with respx.mock(base_url=BAO_ADDR) as mock:
        mock.get("/v1/sys/health").mock(side_effect=httpx.ConnectError("refused"))
        result = await secrets_service.is_healthy()

    assert result is False


# ---------------------------------------------------------------------------
# account_social_path — pure function
# ---------------------------------------------------------------------------

def test_account_social_path():
    path = secrets_service.account_social_path("abc123", "meta")
    assert path == "revos/accounts/abc123/social/meta"

    path2 = secrets_service.account_social_path("xyz-999", "linkedin")
    assert path2 == "revos/accounts/xyz-999/social/linkedin"

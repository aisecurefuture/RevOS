"""Unit tests for the low-cost integration API adapters (Phase 3).

Network calls are mocked with respx. No real credentials.
"""

from __future__ import annotations

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.exceptions import RevOSError
from app.services.integrations import bitly, google_sheets, notion

BITLY_HOST = "https://api-ssl.bitly.com"
NOTION_HOST = "https://api.notion.com"
GOOGLE_TOKEN_HOST = "https://oauth2.googleapis.com"
SHEETS_HOST = "https://sheets.googleapis.com"


# ---------------------------------------------------------------------------
# Bitly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bitly_shorten():
    with respx.mock(base_url=BITLY_HOST) as mock:
        mock.post("/v4/shorten").mock(
            return_value=httpx.Response(200, json={"link": "https://bit.ly/abc123"})
        )
        result = await bitly.shorten("tok", "https://example.com/very/long/path")
    assert result == "https://bit.ly/abc123"


@pytest.mark.asyncio
async def test_bitly_shorten_error():
    with respx.mock(base_url=BITLY_HOST) as mock:
        mock.post("/v4/shorten").mock(
            return_value=httpx.Response(400, json={"message": "INVALID_ARG_LONG_URL"})
        )
        with pytest.raises(RevOSError) as exc:
            await bitly.shorten("tok", "not-a-url")
    assert exc.value.code == "bitly_api_error"


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notion_get_database_schema():
    with respx.mock(base_url=NOTION_HOST) as mock:
        mock.get("/v1/databases/db-1").mock(return_value=httpx.Response(200, json={
            "properties": {"Name": {"type": "title"}, "Email": {"type": "email"}},
        }))
        schema = await notion.get_database_schema("key", "db-1")
    assert schema == {"Name": "title", "Email": "email"}


@pytest.mark.asyncio
async def test_notion_create_page():
    with respx.mock(base_url=NOTION_HOST) as mock:
        mock.post("/v1/pages").mock(return_value=httpx.Response(200, json={"id": "page-1"}))
        page_id = await notion.create_page(
            "key", "db-1", {"Name": "title"}, {"first_name": "Ada", "last_name": "Lovelace"},
        )
    assert page_id == "page-1"


@pytest.mark.asyncio
async def test_notion_create_page_error():
    with respx.mock(base_url=NOTION_HOST) as mock:
        mock.post("/v1/pages").mock(return_value=httpx.Response(400, json={"message": "bad request"}))
        with pytest.raises(RevOSError) as exc:
            await notion.create_page("key", "db-1", {}, {})
    assert exc.value.code == "notion_api_error"


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def _fake_service_account() -> dict:
    """A syntactically valid service account (real RSA key so PyJWT can sign it;
    the token exchange itself is mocked, so the key never touches Google)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {
        "client_email": "svc@project.iam.gserviceaccount.com",
        "private_key": pem,
        "token_uri": f"{GOOGLE_TOKEN_HOST}/token",
    }


def test_parse_service_account_valid():
    import json
    sa = _fake_service_account()
    parsed = google_sheets.parse_service_account(json.dumps(sa))
    assert parsed["client_email"] == sa["client_email"]


def test_parse_service_account_malformed():
    with pytest.raises(RevOSError) as exc:
        google_sheets.parse_service_account("not json")
    assert exc.value.code == "invalid_service_account"


def test_parse_service_account_missing_fields():
    import json
    with pytest.raises(RevOSError) as exc:
        google_sheets.parse_service_account(json.dumps({"client_email": "x@y.com"}))
    assert exc.value.code == "invalid_service_account"


@pytest.mark.asyncio
async def test_get_access_token_signs_valid_jwt_and_exchanges():
    sa = _fake_service_account()

    def _check_request(request):
        # Confirm the assertion is a JWT signed with this service account's key
        # (decodable with its own public key) before returning a fake token.
        body = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        assertion = body["assertion"]
        decoded = jwt.decode(assertion, options={"verify_signature": False})
        assert decoded["iss"] == sa["client_email"]
        assert decoded["scope"] == google_sheets._SCOPE
        return httpx.Response(200, json={"access_token": "at-1"})

    with respx.mock(base_url=GOOGLE_TOKEN_HOST) as mock:
        mock.post("/token").mock(side_effect=_check_request)
        token = await google_sheets.get_access_token(sa)
    assert token == "at-1"


@pytest.mark.asyncio
async def test_append_rows():
    with respx.mock(base_url=SHEETS_HOST) as mock:
        mock.post("/v4/spreadsheets/sheet-1/values/A1:append").mock(
            return_value=httpx.Response(200, json={"updates": {"updatedRows": 2}})
        )
        count = await google_sheets.append_rows("at-1", "sheet-1", [["a", "b"], ["c", "d"]])
    assert count == 2


@pytest.mark.asyncio
async def test_append_rows_error():
    with respx.mock(base_url=SHEETS_HOST) as mock:
        mock.post("/v4/spreadsheets/sheet-1/values/A1:append").mock(
            return_value=httpx.Response(403, json={"error": {"message": "permission denied"}})
        )
        with pytest.raises(RevOSError) as exc:
            await google_sheets.append_rows("at-1", "sheet-1", [["a"]])
    assert exc.value.code == "google_sheets_api_error"

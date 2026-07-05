"""Per-account low-cost integration credentials (Phase 3).

Covers: the credential vault (save/list/remove), provider actions (Bitly
shorten, Notion/Sheets contact push — network calls mocked), the Zapier
show-secret-once pattern, and the per-account inbound webhook signature.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from app.models.user import Role


@pytest.fixture(autouse=True)
def fake_vault():
    """In-memory stand-in for OpenBao so credential save/read/delete round-trips
    without a real Bao instance (tests run with BAO_TOKEN unset)."""
    store: dict[str, dict] = {}

    async def _put(path, data):
        store[path] = data

    async def _get(path):
        return store.get(path)

    async def _delete(path):
        store.pop(path, None)

    with (
        patch("app.services.integration_credentials_service.secrets_service.put_secret", _put),
        patch("app.services.integration_credentials_service.secrets_service.get_secret", _get),
        patch("app.services.integration_credentials_service.secrets_service.delete_secret", _delete),
    ):
        yield store


async def _login(api, email, password):
    r = await api.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _register_owner(api, email="owner@test.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


# ---------------------------------------------------------------------------
# Calendly (no secret) — save / list / remove
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calendly_save_list_remove(api):
    h = await _register_owner(api)

    save = await api.post("/api/integrations/credentials/calendly", headers=h,
                          json={"scheduling_url": "https://calendly.com/me/intro"})
    assert save.status_code == 200, save.text
    assert save.json()["config"]["scheduling_url"] == "https://calendly.com/me/intro"

    listed = (await api.get("/api/integrations/credentials", headers=h)).json()
    assert any(c["provider"] == "calendly" for c in listed)

    rm = await api.delete("/api/integrations/credentials/calendly", headers=h)
    assert rm.status_code == 204

    listed2 = (await api.get("/api/integrations/credentials", headers=h)).json()
    assert not any(c["provider"] == "calendly" for c in listed2)


@pytest.mark.asyncio
async def test_calendly_requires_nonempty_url(api):
    h = await _register_owner(api)
    r = await api.post("/api/integrations/credentials/calendly", headers=h,
                       json={"scheduling_url": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_config"


# ---------------------------------------------------------------------------
# Permission boundary: editor can act, cannot manage credentials
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_editor_cannot_save_credentials(api, make_user):
    await _register_owner(api, "owner2@test.com")
    h = await _login(api, **await make_user("ed@test.com", "EditorPass123", Role.editor))
    r = await api.post("/api/integrations/credentials/calendly", headers=h,
                       json={"scheduling_url": "https://calendly.com/x"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Bitly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bitly_save_and_shorten(api):
    from app.services.integrations import bitly as bitly_client

    h = await _register_owner(api)
    save = await api.post("/api/integrations/credentials/bitly", headers=h,
                          json={"access_token": "tok-1"})
    assert save.status_code == 200, save.text

    with patch.object(bitly_client, "shorten", AsyncMock(return_value="https://bit.ly/abc")):
        r = await api.post("/api/integrations/bitly/shorten", headers=h,
                           json={"url": "https://example.com/long/path"})
    assert r.status_code == 200, r.text
    assert r.json()["short_url"] == "https://bit.ly/abc"


@pytest.mark.asyncio
async def test_bitly_shorten_without_connection_404(api):
    h = await _register_owner(api)
    r = await api.post("/api/integrations/bitly/shorten", headers=h, json={"url": "https://x.com"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notion_push_contacts(api):
    from app.services.integrations import notion as notion_client

    h = await _register_owner(api)
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    await api.post("/api/contacts", headers=h, json={
        "brand_id": bid, "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
    })

    save = await api.post("/api/integrations/credentials/notion", headers=h,
                          json={"api_key": "secret_abc", "database_id": "db-1"})
    assert save.status_code == 200, save.text

    with (
        patch.object(notion_client, "get_database_schema", AsyncMock(return_value={
            "Name": "title", "Email": "email",
        })),
        patch.object(notion_client, "create_page", AsyncMock(return_value="page-1")) as create_mock,
    ):
        r = await api.post(f"/api/integrations/notion/push-contacts?brand_id={bid}", headers=h)

    assert r.status_code == 200, r.text
    assert r.json()["pushed"] == 1
    create_mock.assert_awaited_once()


def test_notion_build_properties_maps_known_fields():
    from app.services.integrations.notion import _build_properties

    schema = {"Name": "title", "Email": "email", "Score": "number", "Notes": "rich_text"}
    contact = {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "lead_score": 42}
    props = _build_properties(schema, contact)

    assert props["Name"]["title"][0]["text"]["content"] == "Ada Lovelace"
    assert props["Email"]["email"] == "ada@example.com"
    assert props["Score"]["number"] == 42
    assert "Notes" not in props  # no matching contact field for an unrelated rich_text column


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

_FAKE_SERVICE_ACCOUNT = json.dumps({
    "client_email": "svc@project.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
    "token_uri": "https://oauth2.googleapis.com/token",
})


@pytest.mark.asyncio
async def test_google_sheets_push_contacts(api):
    from app.services.integrations import google_sheets as sheets_client

    h = await _register_owner(api)
    bid = (await api.post("/api/brands", headers=h, json={"name": "B"})).json()["id"]
    await api.post("/api/contacts", headers=h, json={
        "brand_id": bid, "first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com",
    })

    save = await api.post("/api/integrations/credentials/google-sheets", headers=h, json={
        "service_account_json": _FAKE_SERVICE_ACCOUNT, "spreadsheet_id": "sheet-1",
    })
    assert save.status_code == 200, save.text

    with (
        patch.object(sheets_client, "get_access_token", AsyncMock(return_value="access-tok")),
        patch.object(sheets_client, "append_rows", AsyncMock(return_value=1)) as append_mock,
    ):
        r = await api.post(f"/api/integrations/google-sheets/push-contacts?brand_id={bid}", headers=h)

    assert r.status_code == 200, r.text
    assert r.json()["pushed"] == 1
    append_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_sheets_rejects_malformed_json(api):
    h = await _register_owner(api)
    r = await api.post("/api/integrations/credentials/google-sheets", headers=h, json={
        "service_account_json": "not json", "spreadsheet_id": "sheet-1",
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_service_account"


@pytest.mark.asyncio
async def test_google_sheets_rejects_missing_fields(api):
    h = await _register_owner(api)
    r = await api.post("/api/integrations/credentials/google-sheets", headers=h, json={
        "service_account_json": json.dumps({"client_email": "x@y.com"}),  # missing private_key/token_uri
        "spreadsheet_id": "sheet-1",
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_service_account"


# ---------------------------------------------------------------------------
# Zapier — show-secret-once + rotation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zapier_secret_shown_once_then_hidden(api):
    h = await _register_owner(api)

    first = await api.post("/api/integrations/credentials/zapier", headers=h,
                           json={"outbound_webhook_url": "https://hooks.zapier.com/x"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["inbound_secret"] is not None
    assert "/api/integrations/inbound/contact/" in body["inbound_webhook_url"]

    # Saving again (e.g. just updating the outbound URL) must NOT reveal a
    # secret again — the original is unrecoverable, only rotation returns one.
    second = await api.post("/api/integrations/credentials/zapier", headers=h,
                            json={"outbound_webhook_url": "https://hooks.zapier.com/y"})
    assert second.json()["inbound_secret"] is None


@pytest.mark.asyncio
async def test_zapier_regenerate_secret_rotates(api):
    h = await _register_owner(api)
    first = await api.post("/api/integrations/credentials/zapier", headers=h, json={})
    old_secret = first.json()["inbound_secret"]

    regen = await api.post("/api/integrations/credentials/zapier/regenerate-secret", headers=h)
    assert regen.status_code == 200, regen.text
    new_secret = regen.json()["inbound_secret"]
    assert new_secret != old_secret


# ---------------------------------------------------------------------------
# Inbound webhook — per-account HMAC
# ---------------------------------------------------------------------------

def _sign(secret: str, body: bytes) -> tuple[str, str]:
    ts = str(int(time.time()))
    signed = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return sig, ts


@pytest.mark.asyncio
async def test_inbound_contact_valid_signature_creates_contact(api):
    h = await _register_owner(api)
    me = (await api.get("/api/auth/me", headers=h)).json()

    save = await api.post("/api/integrations/credentials/zapier", headers=h, json={})
    secret = save.json()["inbound_secret"]
    inbound_url = save.json()["inbound_webhook_url"]
    account_id = inbound_url.rsplit("/", 1)[-1]

    payload = {"email": "lead@example.com", "first_name": "New", "source": "zap"}
    body = json.dumps(payload).encode()
    sig, ts = _sign(secret, body)

    r = await api.post(
        f"/api/integrations/inbound/contact/{account_id}",
        content=body,
        headers={"X-Signature": sig, "X-Timestamp": ts, "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert "contact_id" in r.json()


@pytest.mark.asyncio
async def test_inbound_contact_wrong_secret_rejected(api):
    h = await _register_owner(api)
    save = await api.post("/api/integrations/credentials/zapier", headers=h, json={})
    inbound_url = save.json()["inbound_webhook_url"]
    account_id = inbound_url.rsplit("/", 1)[-1]

    body = json.dumps({"email": "x@example.com"}).encode()
    sig, ts = _sign("totally-wrong-secret", body)

    r = await api.post(
        f"/api/integrations/inbound/contact/{account_id}",
        content=body,
        headers={"X-Signature": sig, "X-Timestamp": ts, "Content-Type": "application/json"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_inbound_contact_unconfigured_account_rejected(api):
    import uuid
    r = await api.post(
        f"/api/integrations/inbound/contact/{uuid.uuid4()}",
        content=b"{}",
        headers={"X-Signature": "x", "X-Timestamp": str(int(time.time()))},
    )
    assert r.status_code == 401

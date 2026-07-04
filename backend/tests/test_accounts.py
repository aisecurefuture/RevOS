"""Phase 2 M2 — self-signup, accounts, team creation, and account switching."""

from __future__ import annotations

import contextlib

import pytest
from httpx import ASGITransport, AsyncClient


async def _register(client, email, pw="PassWord1234", name="User"):
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": pw, "full_name": name}
    )
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@contextlib.asynccontextmanager
async def _client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_register_creates_personal_account_and_logs_in(api):
    h = await _register(api, "new@test.com")
    accounts = (await api.get("/api/accounts", headers=h)).json()
    assert len(accounts) == 1
    assert accounts[0]["account"]["type"] == "personal"
    assert accounts[0]["role"] == "owner"
    assert accounts[0]["is_active"] is True
    # and they can immediately create a brand in it
    assert (await api.post("/api/brands", headers=h, json={"name": "B"})).status_code == 201


@pytest.mark.asyncio
async def test_duplicate_email_rejected(api, app):
    await _register(api, "dup@test.com")
    async with _client(app) as c2:
        r = await c2.post(
            "/api/auth/register",
            json={"email": "dup@test.com", "password": "PassWord1234"},
        )
        assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_create_team_switch_and_isolation(api):
    h = await _register(api, "team@test.com")
    # personal brand
    p_brand = (await api.post("/api/brands", headers=h, json={"name": "Personal Brand"})).json()["id"]

    # create a team → now 2 accounts
    team = (await api.post("/api/accounts", headers=h, json={"name": "My Agency"})).json()
    accts = (await api.get("/api/accounts", headers=h)).json()
    assert len(accts) == 2
    personal_id = next(a["account"]["id"] for a in accts if a["account"]["type"] == "personal")

    # switch to the team (re-issues the session), create a brand there
    sw = await api.post("/api/accounts/switch", headers=h, json={"account_id": team["id"]})
    assert sw.status_code == 200
    ht = {"X-CSRF-Token": sw.json()["csrf_token"]}
    t_brand = (await api.post("/api/brands", headers=ht, json={"name": "Team Brand"})).json()["id"]

    # in the team context: see the team brand, NOT the personal one
    team_ids = {b["id"] for b in (await api.get("/api/brands", headers=ht)).json()}
    assert t_brand in team_ids and p_brand not in team_ids

    # switch back to personal: see the personal brand, NOT the team one
    sw2 = await api.post("/api/accounts/switch", headers=ht, json={"account_id": personal_id})
    hp = {"X-CSRF-Token": sw2.json()["csrf_token"]}
    personal_ids = {b["id"] for b in (await api.get("/api/brands", headers=hp)).json()}
    assert p_brand in personal_ids and t_brand not in personal_ids


@pytest.mark.asyncio
async def test_cannot_switch_into_foreign_account(api, app):
    ha = await _register(api, "a@test.com")
    async with _client(app) as cb:
        hb = await _register(cb, "b@test.com")
        b_account = (await cb.get("/api/accounts", headers=hb)).json()[0]["account"]["id"]
    # A is not a member of B's account → switch denied.
    r = await api.post("/api/accounts/switch", headers=ha, json={"account_id": b_account})
    assert r.status_code == 403, r.text

"""Phase 2 M2 — invitations, member role change, and member removal.

Each test uses separate AsyncClient instances (via make_client) so that two
users' CSRF cookies don't collide in a shared client cookie jar.
"""

from __future__ import annotations

import pytest


# --- helpers ----------------------------------------------------------------

async def _register(client, email, pw="PassWord1234", name="Test"):
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": pw, "full_name": name}
    )
    assert r.status_code == 201, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


async def _create_team(client, headers, name="TestTeam"):
    r = await client.post("/api/accounts", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _invite(client, headers, account_id, email, role="viewer"):
    r = await client.post(
        f"/api/accounts/{account_id}/invitations",
        json={"email": email, "role": role},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()  # includes token + accept_url


# --- tests ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invite_and_accept(make_client):
    """Admin invites B by email; B registers with that email and accepts."""
    api_a = await make_client()
    api_b = await make_client()

    h_a = await _register(api_a, "owner@inv.com", name="Owner A")
    team = await _create_team(api_a, h_a)
    account_id = team["id"]

    inv = await _invite(api_a, h_a, account_id, "invitee@inv.com", role="editor")
    assert inv["email"] == "invitee@inv.com"
    assert inv["role"] == "editor"
    token = inv["token"]

    # B registers with the same email
    h_b = await _register(api_b, "invitee@inv.com", name="Invitee B")

    # B accepts the invitation
    accept = await api_b.post(
        "/api/auth/invitation/accept", json={"token": token}, headers=h_b
    )
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["account_id"] == account_id
    assert body["role"] == "editor"

    # B can now see the team in their account list
    accts = (await api_b.get("/api/accounts", headers=h_b)).json()
    ids = [a["account"]["id"] for a in accts]
    assert account_id in ids


@pytest.mark.asyncio
async def test_accept_wrong_email_rejected(make_client):
    """C tries to accept an invite sent to B — rejected because email doesn't match."""
    api_a = await make_client()
    api_c = await make_client()

    h_a = await _register(api_a, "owner@wrongem.com")
    team = await _create_team(api_a, h_a)
    inv = await _invite(api_a, h_a, team["id"], "b@wrongem.com")
    token = inv["token"]

    # C registers with a different email
    h_c = await _register(api_c, "c@wrongem.com")
    r = await api_c.post("/api/auth/invitation/accept", json={"token": token}, headers=h_c)
    assert r.status_code in (403, 404, 422), r.text


@pytest.mark.asyncio
async def test_revoke_invite(make_client):
    """Revoking a pending invite invalidates the token."""
    api_a = await make_client()
    api_b = await make_client()

    h_a = await _register(api_a, "owner@revoke.com")
    team = await _create_team(api_a, h_a)
    inv = await _invite(api_a, h_a, team["id"], "target@revoke.com")
    invite_id = inv["id"]
    token = inv["token"]

    # Revoke
    r = await api_a.delete(
        f"/api/accounts/{team['id']}/invitations/{invite_id}", headers=h_a
    )
    assert r.status_code == 204, r.text

    # Register as invitee and try to accept
    h_b = await _register(api_b, "target@revoke.com")
    r = await api_b.post("/api/auth/invitation/accept", json={"token": token}, headers=h_b)
    assert r.status_code in (404, 403, 410), r.text


@pytest.mark.asyncio
async def test_remove_member(make_client):
    """Owner can remove a non-owner member from the account."""
    api_a = await make_client()
    api_b = await make_client()

    h_a = await _register(api_a, "owner@remove.com")
    team = await _create_team(api_a, h_a)

    # Invite + B accepts
    inv = await _invite(api_a, h_a, team["id"], "member@remove.com")
    h_b = await _register(api_b, "member@remove.com")
    await api_b.post("/api/auth/invitation/accept", json={"token": inv["token"]}, headers=h_b)

    # Get B's user id from the member list
    members = (await api_a.get(f"/api/accounts/{team['id']}/members", headers=h_a)).json()
    b_id = next(m["user_id"] for m in members if m["email"] == "member@remove.com")

    # A removes B
    r = await api_a.delete(
        f"/api/accounts/{team['id']}/members/{b_id}", headers=h_a
    )
    assert r.status_code == 204, r.text

    # B no longer appears in the member list
    members_after = (await api_a.get(f"/api/accounts/{team['id']}/members", headers=h_a)).json()
    assert not any(m["user_id"] == b_id for m in members_after)


@pytest.mark.asyncio
async def test_change_member_role(make_client):
    """Owner can change a member's role."""
    api_a = await make_client()
    api_b = await make_client()

    h_a = await _register(api_a, "owner@rolechg.com")
    team = await _create_team(api_a, h_a)

    inv = await _invite(api_a, h_a, team["id"], "editor@rolechg.com", role="viewer")
    h_b = await _register(api_b, "editor@rolechg.com")
    await api_b.post("/api/auth/invitation/accept", json={"token": inv["token"]}, headers=h_b)

    members = (await api_a.get(f"/api/accounts/{team['id']}/members", headers=h_a)).json()
    b_id = next(m["user_id"] for m in members if m["email"] == "editor@rolechg.com")

    r = await api_a.patch(
        f"/api/accounts/{team['id']}/members/{b_id}",
        json={"role": "editor"},
        headers=h_a,
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "editor"

"""Collaboration assets (CW2) — versioning, comments, two-sided approval, and
the hand-off into the real content/social publishing pipeline.

Consent/approval logic tested at the service level with explicit account ids
(two tenants); the full flow (including the publish hand-off) gets an HTTP
smoke test.
"""

from __future__ import annotations

import uuid

import pytest
from app.core.exceptions import RevOSError
from app.models.brand import Brand
from app.models.collaboration import AssetKind, AssetState
from app.models.matching import CollaborationDirection, CollaborationRequest, CollaborationStatus
from app.models.user import Role
from app.services import workspace_service

ACCT_BRAND = uuid.uuid4()
ACCT_CREATOR = uuid.uuid4()
USER_BRAND = uuid.uuid4()
USER_CREATOR = uuid.uuid4()
OTHER = uuid.uuid4()


async def _collaboration(s):
    req = CollaborationRequest(
        direction=CollaborationDirection.brand_to_creator, status=CollaborationStatus.accepted,
        initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
        recipient_account_id=ACCT_CREATOR, creator_id=uuid.uuid4(), product_id=uuid.uuid4(),
        message="collab?")
    s.add(req)
    await s.flush()
    return await workspace_service.spawn_collaboration(s, req)


async def _asset(s, collab, **kw):
    base = dict(created_by_account_id=ACCT_BRAND, kind=AssetKind.text, title="Post idea",
               caption="Draft v1", media_urls=[])
    base.update(kw)
    return await workspace_service.create_asset(s, collab, **base)


@pytest.mark.asyncio
async def test_create_asset_starts_at_version_one_draft(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        assert asset.current_version == 1 and asset.state == AssetState.draft
        versions = await workspace_service.list_versions(s, asset)
        assert len(versions) == 1 and versions[0].caption == "Draft v1"


@pytest.mark.asyncio
async def test_needs_both_parties_to_approve(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)

        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        assert asset.state == AssetState.in_review   # only one side so far

        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_CREATOR, user_id=USER_CREATOR)
        assert asset.state == AssetState.approved     # both sides now


@pytest.mark.asyncio
async def test_request_changes_overrides_state(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        await workspace_service.request_changes(
            s, asset, collab, account_id=ACCT_CREATOR, user_id=USER_CREATOR, note="tweak the caption")
        assert asset.state == AssetState.changes_requested


@pytest.mark.asyncio
async def test_redeciding_overwrites_not_duplicates(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        await workspace_service.request_changes(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        approvals = await workspace_service.list_approvals(s, asset)
        assert len(approvals) == 1
        assert approvals[0].decision == "changes_requested"


@pytest.mark.asyncio
async def test_new_version_resets_approval_state_without_touching_old_approvals(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_CREATOR, user_id=USER_CREATOR)
        assert asset.state == AssetState.approved

        await workspace_service.add_version(
            s, asset, collab, account_id=ACCT_CREATOR, caption="Draft v2", media_urls=[])
        assert asset.current_version == 2
        assert asset.state == AssetState.draft   # fresh sign-off required

        # v1's approvals still exist, untouched, just no longer relevant.
        v1_approvals = await workspace_service.list_approvals(s, asset, version=1)
        assert len(v1_approvals) == 2
        v2_approvals = await workspace_service.list_approvals(s, asset, version=2)
        assert len(v2_approvals) == 0


@pytest.mark.asyncio
async def test_non_party_cannot_approve_or_comment(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.approve_asset(s, asset, collab, account_id=OTHER, user_id=uuid.uuid4())
        assert exc.value.code == "forbidden"
        with pytest.raises(RevOSError) as exc2:
            await workspace_service.add_comment(
                s, asset, collab, account_id=OTHER, user_id=uuid.uuid4(), body="hi")
        assert exc2.value.code == "forbidden"


@pytest.mark.asyncio
async def test_comments_visible_to_both_parties(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        await workspace_service.add_comment(
            s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND, body="Love this direction")
        await workspace_service.add_comment(
            s, asset, collab, account_id=ACCT_CREATOR, user_id=USER_CREATOR, body="Can we brighten it?")
        comments = await workspace_service.list_comments(s, asset)
        assert len(comments) == 2


@pytest.mark.asyncio
async def test_cannot_publish_unless_approved(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        brand = Brand(name="Ava's Brand", slug="ava-pub", account_id=ACCT_CREATOR)
        s.add(brand)
        await s.flush()

        with pytest.raises(RevOSError) as exc:
            await workspace_service.publish_asset(
                s, asset, collab, actor_account_id=ACCT_CREATOR, brand_id=brand.id, platform="instagram")
        assert exc.value.code == "not_approved"


@pytest.mark.asyncio
async def test_only_creator_side_can_publish(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_CREATOR, user_id=USER_CREATOR)
        brand = Brand(name="Brand Co", slug="brandco-pub", account_id=ACCT_BRAND)
        s.add(brand)
        await s.flush()

        with pytest.raises(RevOSError) as exc:
            await workspace_service.publish_asset(
                s, asset, collab, actor_account_id=ACCT_BRAND, brand_id=brand.id, platform="instagram")
        assert exc.value.code == "forbidden"


@pytest.mark.asyncio
async def test_publish_creates_social_post_from_latest_version(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        asset = await _asset(s, collab, caption="Final caption!", media_urls=["https://x/img.jpg"])
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_BRAND, user_id=USER_BRAND)
        await workspace_service.approve_asset(s, asset, collab, account_id=ACCT_CREATOR, user_id=USER_CREATOR)

        creator_brand = Brand(name="Ava's Brand", slug="ava-pub2", account_id=ACCT_CREATOR)
        s.add(creator_brand)
        await s.flush()

        from app.core.tenancy import set_active_account
        set_active_account(ACCT_CREATOR)   # simulate the creator's own logged-in session
        updated_asset, post = await workspace_service.publish_asset(
            s, asset, collab, actor_account_id=ACCT_CREATOR, brand_id=creator_brand.id,
            platform="instagram")

        assert updated_asset.state == AssetState.published
        assert updated_asset.linked_social_post_id == post.id
        assert post.caption == "Final caption!"
        assert post.media_urls == ["https://x/img.jpg"]
        assert post.account_id == ACCT_CREATOR   # tenant-stamped correctly


# --- HTTP smoke test: full two-sided review flow via the API ----------------
async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_full_asset_review_flow_over_http(make_client, make_user):
    brand_creds = await make_user("abrand@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("acreator@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava", "handle": "@avaasset", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]
    await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch, json={"accept": True})
    wid = (await brand.get("/api/matching/workspaces", headers=bh)).json()[0]["id"]

    asset = (await brand.post(f"/api/matching/workspaces/{wid}/assets", headers=bh, json={
        "kind": "text", "title": "Launch post", "caption": "Check this out!"})).json()
    aid = asset["id"]

    # Creator comments and requests a change; brand revises.
    await creator.post(f"/api/matching/workspaces/{wid}/assets/{aid}/comments", headers=ch,
                       json={"body": "Can we add a CTA?"})
    await creator.post(f"/api/matching/workspaces/{wid}/assets/{aid}/request-changes", headers=ch,
                       json={"note": "needs a CTA"})
    await brand.post(f"/api/matching/workspaces/{wid}/assets/{aid}/versions", headers=bh,
                     json={"caption": "Check this out! Link in bio."})

    # Both approve v2.
    r1 = await brand.post(f"/api/matching/workspaces/{wid}/assets/{aid}/approve", headers=bh, json={})
    assert r1.json()["state"] == "in_review"
    r2 = await creator.post(f"/api/matching/workspaces/{wid}/assets/{aid}/approve", headers=ch, json={})
    assert r2.json()["state"] == "approved"

    # Creator (only they can) publishes to their own account.
    my_brand = (await creator.post("/api/brands", headers=ch, json={
        "name": "Ava Media", "slug": "ava-media-http"})).json()
    published = await creator.post(f"/api/matching/workspaces/{wid}/assets/{aid}/publish", headers=ch,
                                   json={"brand_id": my_brand["id"], "platform": "instagram"})
    assert published.status_code == 200, published.text
    assert published.json()["caption"] == "Check this out! Link in bio."

    got = await brand.get(f"/api/matching/workspaces/{wid}/assets/{aid}", headers=bh)
    assert got.json()["state"] == "published"

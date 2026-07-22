"""Collaboration workspace (CW1) — spawn-on-accept, consent-gated brand-book
sharing (share / read / revoke / auto-revoke-on-end), and offer→product import.

Consent logic is tested at the service level with explicit account ids (two
tenants); spawn-on-accept and offer import get an HTTP smoke test.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from app.core.exceptions import RevOSError
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.brand_book import BrandBook
from app.models.collaboration import Collaboration, CollaborationState, ShareStatus
from app.models.matching import (
    CollaborationDirection,
    CollaborationRequest,
    CollaborationStatus,
    Creator,
    CreatorStatus,
    MatchProduct,
    MatchProductStatus,
)
from app.models.offer import Offer, OfferType
from app.models.user import Role
from app.services import creator_service, workspace_service

ACCT_BRAND = uuid.uuid4()
ACCT_CREATOR = uuid.uuid4()
OTHER = uuid.uuid4()


async def _accepted_request(s, **kw):
    base = dict(
        direction=CollaborationDirection.brand_to_creator, status=CollaborationStatus.accepted,
        initiator_account_id=ACCT_BRAND, initiator_user_id=uuid.uuid4(),
        recipient_account_id=ACCT_CREATOR, creator_id=uuid.uuid4(),
        product_id=uuid.uuid4(), message="collab?")
    base.update(kw)
    req = CollaborationRequest(**base)
    s.add(req)
    await s.flush()
    await s.refresh(req)
    return req


async def _brand_with_book(s, *, account_id=ACCT_BRAND, slug="acme", published=True):
    brand = Brand(name="Acme", slug=slug, account_id=account_id)
    s.add(brand)
    await s.flush()
    s.add(BrandBook(brand_id=brand.id, account_id=account_id, mission="Make great things",
                    positioning="The trustworthy option", is_published=published))
    await s.flush()
    return brand


async def _collaboration(s, **kw):
    req = await _accepted_request(s)
    return await workspace_service.spawn_collaboration(s, req)


@pytest.mark.asyncio
async def test_spawn_is_idempotent(async_session_factory):
    async with async_session_factory() as s:
        req = await _accepted_request(s)
        a = await workspace_service.spawn_collaboration(s, req)
        b = await workspace_service.spawn_collaboration(s, req)
        assert a.id == b.id
        assert a.brand_account_id == ACCT_BRAND and a.creator_account_id == ACCT_CREATOR


@pytest.mark.asyncio
async def test_share_and_read_brand_book(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brand = await _brand_with_book(s)

        share = await workspace_service.share_brand_book(
            s, collab, shared_by_account_id=ACCT_BRAND, brand_id=brand.id)
        assert share.status == ShareStatus.active

        # The OTHER party (creator) can read it.
        book = await workspace_service.resolve_shared_brand_book(s, share, ACCT_CREATOR)
        assert book.mission == "Make great things"


@pytest.mark.asyncio
async def test_cannot_share_a_brand_you_dont_own(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        foreign_brand = await _brand_with_book(s, account_id=OTHER, slug="foreign")
        with pytest.raises(RevOSError) as exc:
            await workspace_service.share_brand_book(
                s, collab, shared_by_account_id=ACCT_BRAND, brand_id=foreign_brand.id)
        assert exc.value.code == "forbidden"


@pytest.mark.asyncio
async def test_non_party_cannot_read_share(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brand = await _brand_with_book(s)
        share = await workspace_service.share_brand_book(
            s, collab, shared_by_account_id=ACCT_BRAND, brand_id=brand.id)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.resolve_shared_brand_book(s, share, OTHER)
        assert exc.value.code == "forbidden"


@pytest.mark.asyncio
async def test_revoke_closes_access(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brand = await _brand_with_book(s)
        share = await workspace_service.share_brand_book(
            s, collab, shared_by_account_id=ACCT_BRAND, brand_id=brand.id)
        await workspace_service.revoke_share(s, share, ACCT_BRAND)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.resolve_shared_brand_book(s, share, ACCT_CREATOR)
        assert exc.value.code == "share_inactive"


@pytest.mark.asyncio
async def test_only_sharer_can_revoke(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brand = await _brand_with_book(s)
        share = await workspace_service.share_brand_book(
            s, collab, shared_by_account_id=ACCT_BRAND, brand_id=brand.id)
        with pytest.raises(RevOSError) as exc:
            await workspace_service.revoke_share(s, share, ACCT_CREATOR)
        assert exc.value.code == "forbidden"


@pytest.mark.asyncio
async def test_ending_collaboration_auto_revokes_shares(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brand = await _brand_with_book(s)
        share = await workspace_service.share_brand_book(
            s, collab, shared_by_account_id=ACCT_BRAND, brand_id=brand.id)

        ended = await workspace_service.end_collaboration(s, collab, ACCT_BRAND)
        assert ended.state == CollaborationState.ended and ended.ended_at is not None
        await s.refresh(share)
        assert share.status == ShareStatus.revoked
        with pytest.raises(RevOSError) as exc:
            await workspace_service.resolve_shared_brand_book(s, share, ACCT_CREATOR)
        assert exc.value.code in ("collaboration_ended", "share_inactive")


@pytest.mark.asyncio
async def test_expired_share_is_not_readable(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        brand = await _brand_with_book(s)
        share = await workspace_service.share_brand_book(
            s, collab, shared_by_account_id=ACCT_BRAND, brand_id=brand.id,
            expires_at=utcnow() - timedelta(hours=1))   # already expired
        with pytest.raises(RevOSError) as exc:
            await workspace_service.resolve_shared_brand_book(s, share, ACCT_CREATOR)
        assert exc.value.code == "share_inactive"


@pytest.mark.asyncio
async def test_product_from_offer_seeds_and_links(async_session_factory):
    async with async_session_factory() as s:
        brand = Brand(name="Acme", slug="acme-off", account_id=ACCT_BRAND)
        s.add(brand)
        await s.flush()
        offer = Offer(brand_id=brand.id, account_id=ACCT_BRAND, name="Premium Course",
                      slug="premium-course", description="A great course.", offer_type=OfferType.product)
        s.add(offer)
        await s.flush()

        product = await creator_service.product_from_offer(
            s, offer, {"industry": "real_estate_agent", "discoverable": True, "status": "active"})
        assert product.name == "Premium Course"
        assert product.description == "A great course."
        assert product.offer_id == offer.id
        assert product.brand_id == brand.id
        assert product.industry == "real_estate_agent" and product.discoverable is True


# --- HTTP: accepting a request opens a workspace visible to both parties -----
async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_accept_spawns_workspace_over_http(make_client, make_user):
    brand_creds = await make_user("wbrand@test.com", "BrandPass123", Role.admin)
    creator_creds = await make_user("wcreator@test.com", "CreatorPass123", Role.admin)
    brand, creator = await make_client(), await make_client()
    bh, ch = await _login(brand, **brand_creds), await _login(creator, **creator_creds)

    cid = (await creator.post("/api/matching/creators", headers=ch, json={
        "display_name": "Ava", "handle": "@avaw", "discoverable": True})).json()["id"]
    pid = (await brand.post("/api/matching/products", headers=bh, json={
        "name": "Staging Co", "status": "active", "discoverable": True})).json()["id"]
    rid = (await brand.post("/api/matching/collaborations", headers=bh, json={
        "direction": "brand_to_creator", "creator_id": cid, "product_id": pid,
        "message": "collab?"})).json()["id"]
    await creator.post(f"/api/matching/collaborations/{rid}/respond", headers=ch,
                       json={"accept": True})

    # Both sides see the spawned workspace.
    for client, hdr in ((brand, bh), (creator, ch)):
        ws = await client.get("/api/matching/workspaces", headers=hdr)
        assert ws.status_code == 200
        assert any(w["collaboration_request_id"] == rid for w in ws.json())

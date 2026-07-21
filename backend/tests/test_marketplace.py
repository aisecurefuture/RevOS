"""Marketplace MK2 — cross-tenant discovery + collaboration request workflow.

Service-level (the API lands in MK3). Rows are seeded with explicit account_ids
to simulate separate tenants; the test engine doesn't enforce FKs, so no Account
rows are needed.
"""

from __future__ import annotations

import re
import uuid

import pytest
from app.core.exceptions import RevOSError
from app.core.tenancy import set_active_account
from app.models.matching import (
    CollaborationDirection,
    CollaborationStatus,
    Creator,
    CreatorStatus,
    MatchProduct,
    MatchProductStatus,
)
from app.services import collaboration_service as cs
from app.services import creator_service

DIR = CollaborationDirection

ACCT_BRAND = uuid.uuid4()
ACCT_CREATOR = uuid.uuid4()
USER_BRAND = uuid.uuid4()
USER_CREATOR = uuid.uuid4()
ADMIN = uuid.uuid4()


async def _creator(s, *, account_id=ACCT_CREATOR, discoverable=True, **kw):
    base = dict(display_name="Ava", handle="@ava", industry="real_estate_agent",
                follower_count=40_000, engagement_rate=0.05, status=CreatorStatus.active,
                discoverable=discoverable, account_id=account_id)
    base.update(kw)
    c = Creator(**base)
    s.add(c)
    await s.flush()
    await s.refresh(c)
    return c


async def _product(s, *, account_id=ACCT_BRAND, discoverable=True, **kw):
    base = dict(name="Staging Co", industry="real_estate_agent", status=MatchProductStatus.active,
                discoverable=discoverable, account_id=account_id)
    base.update(kw)
    p = MatchProduct(**base)
    s.add(p)
    await s.flush()
    await s.refresh(p)
    return p


@pytest.fixture(autouse=True)
def _no_active_account():
    set_active_account(None)  # keep explicit account_ids; don't auto-stamp
    yield


@pytest.mark.asyncio
async def test_brand_to_creator_request_succeeds(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s)
        req = await cs.create_request(
            s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
            direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id,
            message="Love your work — collab?")
        assert req.status == CollaborationStatus.pending
        assert req.recipient_account_id == ACCT_CREATOR
        assert req.expires_at is not None


@pytest.mark.asyncio
async def test_cannot_reach_non_discoverable_creator_cross_tenant(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s, discoverable=False)
        product = await _product(s)
        with pytest.raises(RevOSError) as e:
            await cs.create_request(
                s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
                direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id,
                message="hi")
        assert e.value.code == "not_discoverable"


@pytest.mark.asyncio
async def test_cannot_reach_out_with_someone_elses_product(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s, account_id=uuid.uuid4())   # not the initiator's
        with pytest.raises(RevOSError) as e:
            await cs.create_request(
                s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
                direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id,
                message="hi")
        assert e.value.code == "forbidden"


@pytest.mark.asyncio
async def test_duplicate_pending_request_blocked(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s)
        kw = dict(initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
                  direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id,
                  message="hi")
        await cs.create_request(s, **kw)
        with pytest.raises(RevOSError) as e:
            await cs.create_request(s, **kw)
        assert e.value.code == "duplicate_request"


@pytest.mark.asyncio
async def test_daily_rate_limit(async_session_factory, monkeypatch):
    monkeypatch.setattr(cs, "MAX_REQUESTS_PER_DAY", 2)
    async with async_session_factory() as s:
        product = await _product(s)
        for i in range(2):
            c = await _creator(s, handle=f"@c{i}")
            await cs.create_request(
                s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
                direction=DIR.brand_to_creator, creator_id=c.id, product_id=product.id, message="hi")
        c3 = await _creator(s, handle="@c3")
        with pytest.raises(RevOSError) as e:
            await cs.create_request(
                s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
                direction=DIR.brand_to_creator, creator_id=c3.id, product_id=product.id, message="hi")
        assert e.value.code == "rate_limited"


@pytest.mark.asyncio
async def test_respond_accept_then_not_pending(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s)
        req = await cs.create_request(
            s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
            direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id, message="hi")
        done = await cs.respond(s, req, accept=True, note="yes!", channel="in_app")
        assert done.status == CollaborationStatus.accepted and done.responded_at is not None
        with pytest.raises(RevOSError) as e:
            await cs.respond(s, req, accept=False)
        assert e.value.code == "not_pending"


@pytest.mark.asyncio
async def test_withdraw_authz(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s)
        req = await cs.create_request(
            s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
            direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id, message="hi")
        with pytest.raises(RevOSError) as e:
            await cs.withdraw(s, req, actor_account_id=uuid.uuid4())   # not the sender
        assert e.value.code == "forbidden"
        pulled = await cs.withdraw(s, req, actor_account_id=ACCT_BRAND)
        assert pulled.status == CollaborationStatus.withdrawn


@pytest.mark.asyncio
async def test_respond_via_emailed_token(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s)
        req = await cs.create_request(
            s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
            direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id, message="hi")
        url = cs.make_respond_url(req.id, accept=True)
        token = re.search(r"token=([^\"'&]+)", url).group(1)
        done = await cs.respond_via_token(s, token)
        assert done.status == CollaborationStatus.accepted and done.response_channel == "email"


@pytest.mark.asyncio
async def test_admin_broker_bypasses_discoverable_and_ownership(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s, discoverable=False)               # hidden
        product = await _product(s, account_id=uuid.uuid4())          # not the initiator's
        req = await cs.create_request(
            s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
            direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id,
            message="intro", brokered_by_user_id=ADMIN)
        assert req.status == CollaborationStatus.pending and req.brokered_by_user_id == ADMIN


@pytest.mark.asyncio
async def test_creator_to_brand_requires_discoverable_product(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s, account_id=ACCT_CREATOR)
        hidden = await _product(s, account_id=uuid.uuid4(), discoverable=False)
        with pytest.raises(RevOSError) as e:
            await cs.create_request(
                s, initiator_account_id=ACCT_CREATOR, initiator_user_id=USER_CREATOR,
                direction=DIR.creator_to_brand, creator_id=creator.id, product_id=hidden.id,
                message="I'd love to work with you")
        assert e.value.code == "not_discoverable"


@pytest.mark.asyncio
async def test_cross_tenant_search_respects_discoverable(async_session_factory):
    async with async_session_factory() as s:
        await _creator(s, handle="@shown", discoverable=True)
        await _creator(s, handle="@hidden", discoverable=False)
        set_active_account(ACCT_BRAND)   # searching as the brand tenant
        try:
            visible = await creator_service.search_discoverable_creators(s)
            handles = {r["creator"].handle for r in visible}
            assert "@shown" in handles and "@hidden" not in handles
            # Admin broker view sees hidden creators too.
            allc = await creator_service.search_discoverable_creators(s, include_hidden=True)
            assert "@hidden" in {r["creator"].handle for r in allc}
        finally:
            set_active_account(None)


@pytest.mark.asyncio
async def test_inboxes_split_incoming_and_outgoing(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        product = await _product(s)
        await cs.create_request(
            s, initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
            direction=DIR.brand_to_creator, creator_id=creator.id, product_id=product.id, message="hi")
        outgoing = await cs.list_for_account(s, ACCT_BRAND, box="outgoing")
        incoming = await cs.list_for_account(s, ACCT_CREATOR, box="incoming")
        assert len(outgoing) == 1 and len(incoming) == 1
        assert await cs.list_for_account(s, ACCT_BRAND, box="incoming") == []

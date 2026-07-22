"""Insights CW4 — per-collaboration outcomes rolled into the IK1 dashboards."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from app.models.base import utcnow
from app.models.collaboration import (
    AssetKind,
    Collaboration,
    CollaborationDeliverable,
    CollaborationState,
    DeliverableStatus,
)
from app.models.matching import Creator, CreatorStatus, MatchProduct, MatchProductStatus
from app.services import insights_service, workspace_service

ACCT_CREATOR = uuid.uuid4()
ACCT_BRAND = uuid.uuid4()


async def _creator(s):
    c = Creator(display_name="Ava", account_id=ACCT_CREATOR, status=CreatorStatus.active,
               discoverable=True)
    s.add(c)
    await s.flush()
    return c


async def _collaboration(s, creator, *, state=CollaborationState.active):
    collab = Collaboration(
        collaboration_request_id=uuid.uuid4(), brand_account_id=ACCT_BRAND,
        creator_account_id=ACCT_CREATOR, creator_id=creator.id, state=state)
    s.add(collab)
    await s.flush()
    return collab


@pytest.mark.asyncio
async def test_rollup_zero_state_for_no_collaborations(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        result = await insights_service.creator_insights(s, creator, now=utcnow())
        m = result["metrics"]
        assert m["collaborations_total"] == 0
        assert m["published_assets"] == 0
        assert m["deliverables_total"] == 0


@pytest.mark.asyncio
async def test_rollup_counts_collaborations_and_published_assets(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        collab1 = await _collaboration(s, creator)
        await _collaboration(s, creator, state=CollaborationState.ended)

        asset = await workspace_service.create_asset(
            s, collab1, created_by_account_id=ACCT_BRAND, kind=AssetKind.text, title="Post",
            caption="draft", media_urls=[])
        await workspace_service.approve_asset(s, asset, collab1, account_id=ACCT_BRAND, user_id=uuid.uuid4())
        await workspace_service.approve_asset(s, asset, collab1, account_id=ACCT_CREATOR, user_id=uuid.uuid4())

        brand = None
        from app.models.brand import Brand
        brand = Brand(name="Ava Media", slug="ava-cw4", account_id=ACCT_CREATOR)
        s.add(brand)
        await s.flush()
        from app.core.tenancy import set_active_account
        set_active_account(ACCT_CREATOR)
        await workspace_service.publish_asset(
            s, asset, collab1, actor_account_id=ACCT_CREATOR, brand_id=brand.id, platform="instagram")

        result = await insights_service.creator_insights(s, creator, now=utcnow())
        m = result["metrics"]
        assert m["collaborations_total"] == 2
        assert m["collaborations_active"] == 1
        assert m["published_assets"] == 1


@pytest.mark.asyncio
async def test_overdue_deliverable_triggers_high_priority_recommendation(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        collab = await _collaboration(s, creator)
        s.add(CollaborationDeliverable(
            collaboration_id=collab.id, created_by_account_id=ACCT_BRAND, title="Late post",
            status=DeliverableStatus.pending, due_at=utcnow() - timedelta(days=2)))
        s.add(CollaborationDeliverable(
            collaboration_id=collab.id, created_by_account_id=ACCT_BRAND, title="On-time post",
            status=DeliverableStatus.approved, due_at=utcnow() - timedelta(days=2),
            completed_at=utcnow()))
        await s.flush()

        result = await insights_service.creator_insights(s, creator, now=utcnow())
        assert result["metrics"]["deliverables_overdue"] == 1
        assert result["metrics"]["deliverables_total"] == 2
        assert result["metrics"]["deliverables_approved"] == 1
        titles = [r["title"] for r in result["recommendations"]]
        assert "You have overdue deliverables" in titles
        rec = next(r for r in result["recommendations"] if r["title"] == "You have overdue deliverables")
        assert rec["priority"] == "high"


@pytest.mark.asyncio
async def test_underway_but_nothing_published_recommendation(async_session_factory):
    async with async_session_factory() as s:
        creator = await _creator(s)
        await _collaboration(s, creator)
        result = await insights_service.creator_insights(s, creator, now=utcnow())
        titles = [r["title"] for r in result["recommendations"]]
        assert "Get a draft over the finish line" in titles


@pytest.mark.asyncio
async def test_product_rollup_uses_product_id(async_session_factory):
    async with async_session_factory() as s:
        product = MatchProduct(name="Staging Co", account_id=ACCT_BRAND, status=MatchProductStatus.active,
                               discoverable=True)
        s.add(product)
        await s.flush()
        collab = Collaboration(
            collaboration_request_id=uuid.uuid4(), brand_account_id=ACCT_BRAND,
            creator_account_id=ACCT_CREATOR, creator_id=uuid.uuid4(), product_id=product.id,
            state=CollaborationState.active)
        s.add(collab)
        await s.flush()

        result = await insights_service.product_insights(s, product, now=utcnow())
        assert result["metrics"]["collaborations_total"] == 1

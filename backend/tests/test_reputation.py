"""Reputation RK1 — certification + review models (data layer only; the rating
engine is RK2 and the feedback workflow API is RK3).

Rows are seeded with explicit account_ids to simulate separate tenants, same
pattern as test_marketplace.py.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.matching import (
    CollaborationDirection,
    CollaborationRequest,
    CollaborationStatus,
    Creator,
    CreatorStatus,
    MatchProduct,
    MatchProductStatus,
)
from app.models.reputation import (
    Certification,
    CertificationSubjectType,
    Review,
    ReviewDirection,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

ACCT_BRAND = uuid.uuid4()
ACCT_CREATOR = uuid.uuid4()
USER_BRAND = uuid.uuid4()
USER_CREATOR = uuid.uuid4()


async def _collaboration(s, **kw):
    base = dict(
        direction=CollaborationDirection.brand_to_creator, status=CollaborationStatus.accepted,
        initiator_account_id=ACCT_BRAND, initiator_user_id=USER_BRAND,
        creator_id=uuid.uuid4(), message="hi",
    )
    base.update(kw)
    req = CollaborationRequest(**base)
    s.add(req)
    await s.flush()
    await s.refresh(req)
    return req


@pytest.mark.asyncio
async def test_certification_attaches_to_creator_and_product(async_session_factory):
    async with async_session_factory() as s:
        creator = Creator(display_name="Ava", account_id=ACCT_CREATOR, status=CreatorStatus.active)
        product = MatchProduct(name="Staging Co", account_id=ACCT_BRAND, status=MatchProductStatus.active)
        s.add(creator)
        s.add(product)
        await s.flush()

        s.add(Certification(
            account_id=ACCT_CREATOR, subject_type=CertificationSubjectType.creator,
            subject_id=creator.id, name="Verified Real Estate License", issuer="TREC",
        ))
        s.add(Certification(
            account_id=ACCT_BRAND, subject_type=CertificationSubjectType.match_product,
            subject_id=product.id, name="BBB Accredited", verified=True,
        ))
        await s.flush()

        rows = (await s.execute(select(Certification))).scalars().all()
        assert len(rows) == 2
        by_type = {c.subject_type: c for c in rows}
        assert by_type[CertificationSubjectType.creator].subject_id == creator.id
        assert by_type[CertificationSubjectType.match_product].verified is True


@pytest.mark.asyncio
async def test_review_requires_a_real_collaboration(async_session_factory):
    async with async_session_factory() as s:
        creator = Creator(display_name="Ava", account_id=ACCT_CREATOR, status=CreatorStatus.active)
        s.add(creator)
        await s.flush()
        collab = await _collaboration(s, creator_id=creator.id)

        review = Review(
            collaboration_request_id=collab.id, direction=ReviewDirection.brand_reviews_creator,
            reviewer_account_id=ACCT_BRAND, reviewer_user_id=USER_BRAND,
            subject_creator_id=creator.id, rating=5,
            dimension_ratings={"communication": 5, "reliability": 4},
            comment="Great to work with.",
        )
        s.add(review)
        await s.flush()
        await s.refresh(review)
        assert review.rating == 5
        assert review.dimension_ratings["communication"] == 5


@pytest.mark.asyncio
async def test_review_rating_out_of_range_rejected(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        s.add(Review(
            collaboration_request_id=collab.id, direction=ReviewDirection.brand_reviews_creator,
            reviewer_account_id=ACCT_BRAND, reviewer_user_id=USER_BRAND, rating=7,
        ))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_one_review_per_collaboration_per_reviewer(async_session_factory):
    async with async_session_factory() as s:
        collab = await _collaboration(s)
        s.add(Review(
            collaboration_request_id=collab.id, direction=ReviewDirection.brand_reviews_creator,
            reviewer_account_id=ACCT_BRAND, reviewer_user_id=USER_BRAND, rating=5,
        ))
        await s.flush()
        s.add(Review(
            collaboration_request_id=collab.id, direction=ReviewDirection.brand_reviews_creator,
            reviewer_account_id=ACCT_BRAND, reviewer_user_id=USER_BRAND, rating=1,
        ))
        with pytest.raises(IntegrityError):
            await s.flush()


@pytest.mark.asyncio
async def test_subject_can_respond_to_a_review(async_session_factory):
    from app.models.base import utcnow

    async with async_session_factory() as s:
        collab = await _collaboration(s)
        review = Review(
            collaboration_request_id=collab.id, direction=ReviewDirection.brand_reviews_creator,
            reviewer_account_id=ACCT_BRAND, reviewer_user_id=USER_BRAND, rating=2,
            comment="Slow to respond.",
        )
        s.add(review)
        await s.flush()

        review.response = "We had a family emergency that week — back to normal now."
        review.response_at = utcnow()
        s.add(review)
        await s.flush()
        await s.refresh(review)
        assert review.response is not None
        assert review.response_at is not None

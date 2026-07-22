"""Review feedback workflow (Phase 3, RK3).

Reviews are earned, not free — a review may only be submitted by a party to a
real, ACCEPTED collaboration, about the other side, once. That constraint (plus
the DB unique constraint on collaboration+reviewer as a backstop) is what makes
reviews meaningful input to the reputation engine (RK2).

Direction and subject are derived from the collaboration, not accepted as
caller input — a party can't claim to be reviewing someone they didn't actually
collaborate with.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.exceptions import RevOSError
from app.models.base import utcnow
from app.models.matching import CollaborationDirection, CollaborationRequest, CollaborationStatus
from app.models.reputation import Review, ReviewDirection


def _review_direction_and_subject(
    collab: CollaborationRequest, reviewer_account_id: uuid.UUID,
) -> tuple[ReviewDirection, uuid.UUID | None, uuid.UUID | None]:
    """Who is reviewing whom, derived from the collaboration's two fixed
    parties — never from caller-supplied input."""
    brand_account = (collab.initiator_account_id
                     if collab.direction == CollaborationDirection.brand_to_creator
                     else collab.recipient_account_id)
    if reviewer_account_id == brand_account:
        return ReviewDirection.brand_reviews_creator, collab.creator_id, None
    creator_account = (collab.recipient_account_id
                       if collab.direction == CollaborationDirection.brand_to_creator
                       else collab.initiator_account_id)
    if reviewer_account_id == creator_account:
        return ReviewDirection.creator_reviews_brand, None, collab.product_id
    raise RevOSError("You are not a party to this collaboration.", code="forbidden", status_code=403)


async def submit_review(
    db: AsyncSession, collab: CollaborationRequest, *,
    reviewer_account_id: uuid.UUID, reviewer_user_id: uuid.UUID,
    rating: int, dimension_ratings: dict | None = None, comment: str | None = None,
) -> Review:
    if collab.status != CollaborationStatus.accepted:
        raise RevOSError("Only accepted collaborations can be reviewed.",
                         code="not_reviewable", status_code=409)

    direction, subject_creator_id, subject_product_id = _review_direction_and_subject(
        collab, reviewer_account_id)

    existing = (await db.execute(
        select(Review).where(
            Review.collaboration_request_id == collab.id,
            Review.reviewer_account_id == reviewer_account_id,
            Review.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise RevOSError("You already reviewed this collaboration.",
                         code="already_reviewed", status_code=409)

    review = Review(
        collaboration_request_id=collab.id, direction=direction,
        reviewer_account_id=reviewer_account_id, reviewer_user_id=reviewer_user_id,
        subject_creator_id=subject_creator_id, subject_product_id=subject_product_id,
        rating=rating, dimension_ratings=dimension_ratings or {}, comment=comment,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return review


async def respond_to_review(
    db: AsyncSession, review: Review, *, actor_account_id: uuid.UUID, response: str,
) -> Review:
    """Only the reviewed party (the subject's own account) may post the public
    reply — never the reviewer, and never a third party."""
    from app.models.matching import Creator, MatchProduct

    if review.subject_creator_id is not None:
        subject = await db.get(Creator, review.subject_creator_id)
    else:
        subject = await db.get(MatchProduct, review.subject_product_id)
    if subject is None or subject.account_id != actor_account_id:
        raise RevOSError("Only the reviewed party can respond to this review.",
                         code="forbidden", status_code=403)
    if review.response is not None:
        raise RevOSError("This review already has a response.", code="already_responded", status_code=409)

    review.response = response.strip()
    review.response_at = utcnow()
    db.add(review)
    await db.flush()
    await db.refresh(review)
    return review


async def list_for_collaboration(db: AsyncSession, collaboration_request_id: uuid.UUID) -> list[Review]:
    stmt = select(Review).where(
        Review.collaboration_request_id == collaboration_request_id, Review.deleted_at.is_(None),
    ).order_by(Review.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_for_subject(
    db: AsyncSession, *, subject_type: str, subject_id: uuid.UUID, limit: int = 50, offset: int = 0,
) -> list[Review]:
    subject_col = Review.subject_creator_id if subject_type == "creator" else Review.subject_product_id
    stmt = select(Review).where(
        subject_col == subject_id, Review.deleted_at.is_(None),
    ).order_by(Review.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def pending_review_prompts(db: AsyncSession, account_id: uuid.UUID) -> list[CollaborationRequest]:
    """Accepted collaborations this account was a party to, but hasn't reviewed
    yet — the "prompt both sides to review" surface the roadmap calls for."""
    from sqlmodel import or_

    already = select(Review.collaboration_request_id).where(
        Review.reviewer_account_id == account_id, Review.deleted_at.is_(None))
    stmt = select(CollaborationRequest).where(
        or_(CollaborationRequest.initiator_account_id == account_id,
            CollaborationRequest.recipient_account_id == account_id),
        CollaborationRequest.status == CollaborationStatus.accepted,
        CollaborationRequest.deleted_at.is_(None),
        CollaborationRequest.id.not_in(already),
    ).order_by(CollaborationRequest.responded_at.desc()).limit(50)
    return list((await db.execute(stmt)).scalars().all())

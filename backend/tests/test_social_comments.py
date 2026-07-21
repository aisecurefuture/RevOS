"""Approval-gated social comment replies (Facebook + Instagram)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.social import SocialPlatform
from app.models.social_comment import SocialComment, SocialCommentStatus
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.services import social_comment_service as svc
from app.services.social.meta import IncomingComment


# ---------------------------------------------------------------------------
# Relevance filter (pure)
# ---------------------------------------------------------------------------

def test_relevance_keeps_questions_and_substantive():
    assert svc.is_relevant("Is this still for sale?", author_id=None, page_ids=set())[0] is True
    assert svc.is_relevant("I really love this kitchen", author_id=None, page_ids=set())[0] is True


def test_relevance_skips_emoji_spam_and_own():
    assert svc.is_relevant("🔥🔥🔥", author_id=None, page_ids=set())[0] is False
    assert svc.is_relevant("Follow me for free followers!", author_id=None, page_ids=set())[0] is False
    assert svc.is_relevant("check my profile", author_id=None, page_ids=set())[0] is False
    assert svc.is_relevant("nice", author_id="PAGE1", page_ids={"PAGE1"})[0] is False  # own comment
    assert svc.is_relevant("", author_id=None, page_ids=set())[0] is False
    assert svc.is_relevant("ok", author_id=None, page_ids=set())[0] is False  # too short


def test_reply_prompt_includes_persona_and_forbids_pii():
    system, context = svc.build_reply_prompt(
        brand_name="Acme Realty", voice="warm", persona="Hao (calm, expert)",
        comment_text="Any open houses this weekend?",
    )
    assert "Acme Realty" in system
    assert "Hao (calm, expert)" in system
    assert "personal characteristics" in system  # anti-PII / fair-housing guardrail
    assert "Any open houses" in context


# ---------------------------------------------------------------------------
# Full lifecycle: ingest → draft → approve → reply (mocked adapter + AI)
# ---------------------------------------------------------------------------

async def _register_owner(api, async_session_factory, email="owner@comments.com"):
    r = await api.post("/api/auth/register", json={
        "email": email, "password": "OwnerPass123", "full_name": "Owner",
    })
    assert r.status_code == 201, r.text
    # Approving requires a verified email.
    from sqlalchemy import select

    from app.models.base import utcnow
    from app.models.user import AdminUser
    async with async_session_factory() as s:
        user = (await s.execute(select(AdminUser).where(AdminUser.email == email))).scalar_one()
        user.email_verified_at = utcnow()
        s.add(user)
        await s.commit()
    return {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_full_comment_reply_lifecycle(api, async_session_factory, monkeypatch):
    monkeypatch.setattr(svc.settings, "social_comment_replies_enabled", True)
    # Deterministic AI + secret + Meta adapter.
    monkeypatch.setattr(svc.ai_service, "generate", lambda **_: "Thanks for asking — yes, it's available! DM us for a showing.")
    monkeypatch.setattr(svc.secrets_service, "get_secret", AsyncMock(return_value={
        "access_token": "PAGE_TOKEN", "page_id": "PAGE1",
    }))
    monkeypatch.setattr(svc.meta_client, "list_page_comments", AsyncMock(return_value=[
        IncomingComment("POST1", "CMT_SPAM", "follow me for free followers", "Bot", "B1", None, None),
        IncomingComment("POST1", "CMT_GOOD", "Is this home still available?", "Jane", "J1", "http://fb/x", None),
    ]))
    reply_mock = AsyncMock(return_value="REPLY99")
    monkeypatch.setattr(svc.meta_client, "reply_to_page_comment", reply_mock)

    h = await _register_owner(api, async_session_factory)
    accounts = (await api.get("/api/accounts", headers=h)).json()
    account_id = uuid.UUID(accounts[0]["account"]["id"])

    async with async_session_factory() as s:
        conn = SocialConnection(
            account_id=account_id, platform=SocialPlatform.facebook,
            external_id="PAGE1", status=SocialConnectionStatus.active,
            token_ref="revos/x/facebook/1", connected_by=uuid.uuid4(),
        )
        s.add(conn)
        await s.commit()
        await s.refresh(conn)

        drafts = await svc.ingest_for_connection(s, conn)
        await s.commit()
        assert drafts == 1  # spam filtered, question drafted

    # The inbox shows both (spam ignored, question drafted); one approval pending.
    inbox = (await api.get("/api/social-comments", headers=h)).json()
    statuses = {c["external_comment_id"] if "external_comment_id" in c else c["text"]: c["status"] for c in inbox}
    assert any(c["status"] == "drafted" and c["drafted_reply"] for c in inbox)
    assert any(c["status"] == "ignored" for c in inbox)

    pending = (await api.get("/api/approvals", headers=h)).json()
    reply_approvals = [a for a in pending if a["action_type"] == "social_comment_reply"]
    assert len(reply_approvals) == 1
    approval_id = reply_approvals[0]["id"]

    # Approve → the reply posts via the adapter.
    r = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
    assert r.status_code == 200, r.text
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[0] == "CMT_GOOD"  # replied to the right comment

    async with async_session_factory() as s:
        row = (await s.execute(
            __import__("sqlalchemy").select(SocialComment).where(SocialComment.external_comment_id == "CMT_GOOD")
        )).scalar_one()
        assert row.status == SocialCommentStatus.replied
        assert row.reply_external_id == "REPLY99"


@pytest.mark.asyncio
async def test_edit_draft_then_approve_posts_edited_text(api, async_session_factory, monkeypatch):
    monkeypatch.setattr(svc.settings, "social_comment_replies_enabled", True)
    monkeypatch.setattr(svc.ai_service, "generate", lambda **_: "Original drafted reply.")
    monkeypatch.setattr(svc.secrets_service, "get_secret", AsyncMock(return_value={
        "access_token": "PAGE_TOKEN", "page_id": "PAGE1",
    }))
    monkeypatch.setattr(svc.meta_client, "list_page_comments", AsyncMock(return_value=[
        IncomingComment("POST1", "CMT_EDIT", "When can I tour it?", "Sam", "S1", None, None),
    ]))
    reply_mock = AsyncMock(return_value="REPLY_EDITED")
    monkeypatch.setattr(svc.meta_client, "reply_to_page_comment", reply_mock)

    h = await _register_owner(api, async_session_factory, "editor@comments.com")
    account_id = uuid.UUID((await api.get("/api/accounts", headers=h)).json()[0]["account"]["id"])

    async with async_session_factory() as s:
        conn = SocialConnection(
            account_id=account_id, platform=SocialPlatform.facebook, external_id="PAGE1",
            status=SocialConnectionStatus.active, token_ref="revos/x/fb/2", connected_by=uuid.uuid4(),
        )
        s.add(conn)
        await s.commit()
        await s.refresh(conn)
        await svc.ingest_for_connection(s, conn)
        await s.commit()
        comment_id = (await s.execute(
            __import__("sqlalchemy").select(SocialComment).where(SocialComment.external_comment_id == "CMT_EDIT")
        )).scalar_one().id

    # Edit the draft.
    r = await api.post(f"/api/social-comments/{comment_id}/draft", headers=h,
                       json={"reply_text": "Happy to help — tours are available this Saturday, just DM us!"})
    assert r.status_code == 200, r.text
    assert "Saturday" in r.json()["drafted_reply"]

    # Empty edit rejected.
    assert (await api.post(f"/api/social-comments/{comment_id}/draft", headers=h,
                           json={"reply_text": "   "})).status_code == 400

    # Approve → the EDITED text is what posts.
    pending = (await api.get("/api/approvals", headers=h)).json()
    approval_id = [a for a in pending if a["action_type"] == "social_comment_reply"][0]["id"]
    r = await api.post(f"/api/approvals/{approval_id}/approve", headers=h)
    assert r.status_code == 200, r.text
    assert "Saturday" in reply_mock.await_args.args[2]  # edited text, not the original draft


@pytest.mark.asyncio
async def test_like_is_facebook_only(api, async_session_factory, monkeypatch):
    monkeypatch.setattr(svc.secrets_service, "get_secret", AsyncMock(return_value={"access_token": "T", "page_id": "P"}))
    like_mock = AsyncMock()
    monkeypatch.setattr(svc.meta_client, "like_page_comment", like_mock)

    h = await _register_owner(api, async_session_factory, "owner2@comments.com")
    account_id = uuid.UUID((await api.get("/api/accounts", headers=h)).json()[0]["account"]["id"])

    async with async_session_factory() as s:
        conn = SocialConnection(
            account_id=account_id, platform=SocialPlatform.instagram, external_id="IG1",
            status=SocialConnectionStatus.active, token_ref="revos/x/ig/1", connected_by=uuid.uuid4(),
        )
        s.add(conn)
        await s.flush()
        ig_comment = SocialComment(
            account_id=account_id, connection_id=conn.id, platform=str(SocialPlatform.instagram),
            external_post_id="M1", external_comment_id="IGC1", text="love it",
            status=SocialCommentStatus.drafted,
        )
        s.add(ig_comment)
        await s.commit()
        ig_id = ig_comment.id

    # IG like is unsupported → 400, adapter never called.
    r = await api.post(f"/api/social-comments/{ig_id}/like", headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "like_unsupported"
    like_mock.assert_not_awaited()

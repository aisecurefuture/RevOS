"""Approval-gated social comment replies (Facebook Pages + Instagram + YouTube).

Pipeline, all human-gated:

  1. ``ingest_for_connection`` — poll a connection's recent comments (Meta
     Graph), dedupe by external id, run each through the RELEVANCE FILTER
     (skip spam / emoji-only / the brand's own comments / stale), and store
     the keepers as SocialComment rows.
  2. ``draft_reply`` — for a stored comment, generate a reply grounded in the
     brand voice + (optional) Persona, screened by the Fair Housing guard,
     and open an ApprovalRequest(action=social_comment_reply). Nothing is
     posted yet.
  3. ``execute_reply`` — called by the approval dispatcher AFTER a human
     approves; posts the reply via the adapter.
  4. ``like_comment`` — one-click like (Facebook only; Instagram and YouTube
     have no like-comment API).

Reuses the exact token/secret + adapter plumbing publishing already uses.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError, RevOSError
from app.models.approval import ApprovalAction, ApprovalRequest, ApprovalStatus
from app.models.base import utcnow
from app.models.brand import Brand
from app.models.persona_identity import PersonaIdentity, PersonaIdentityStatus
from app.models.social import SocialPlatform
from app.models.social_comment import SocialComment, SocialCommentStatus
from app.models.social_connection import SocialConnection, SocialConnectionStatus
from app.services import ai_service, brand_service, secrets_service
from app.services.social import meta as meta_client
from app.services.social import threads as threads_client
from app.services.social import youtube as youtube_client
from app.services.social.meta import IncomingComment

logger = logging.getLogger("revos.social.comments")

# The steering/Fair-Housing guard from listing videos is a good general filter
# on public brand speech (it targets people-descriptions, not product), so we
# reuse it to strip risky auto-drafted replies.
from app.services.listing_video_service import fair_housing_flags  # noqa: E402


# ---------------------------------------------------------------------------
# Relevance filter (pure, unit-testable)
# ---------------------------------------------------------------------------

_EMOJI_PUNCT_ONLY = re.compile(r"^[\s\W_]*$", re.UNICODE)
_SPAM_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bfollow\s+me\b", r"\bcheck\s+my\s+(page|profile|bio)\b", r"\bfree\s+followers\b",
    r"\bdm\s+me\s+for\b.*\b(promo|collab|deal)\b", r"\bwww\.\w+", r"https?://",
    r"\bcrypto\b", r"\binvest\b.*\bprofit\b", r"\b(viagra|casino|loan)\b",
))


def is_relevant(text: str, *, author_id: str | None, page_ids: set[str]) -> tuple[bool, str]:
    """Decide whether a comment is worth an AI-drafted reply.

    Returns (keep, note). Conservative on the SKIP side — a flooded approval
    queue is worse than missing a low-value comment.
    """
    t = (text or "").strip()
    if author_id and author_id in page_ids:
        return False, "Your own comment"
    if not t:
        return False, "Empty comment"
    if _EMOJI_PUNCT_ONLY.match(t):
        return False, "Emoji/reaction only"
    for rx in _SPAM_PATTERNS:
        if rx.search(t):
            return False, "Looks like spam/self-promotion"
    letters = sum(c.isalpha() for c in t)
    if letters < 4:
        return False, "Too short to reply to"
    # A question, or a substantive statement (>= 3 words) is worth a reply.
    if "?" in t or len(t.split()) >= 3:
        return True, "Question" if "?" in t else "Substantive comment"
    return False, "Low-signal comment"


# ---------------------------------------------------------------------------
# Reply drafting prompt (pure)
# ---------------------------------------------------------------------------

def build_reply_prompt(*, brand_name: str, voice: str | None, persona: str | None, comment_text: str) -> tuple[str, str]:
    system = (
        f"You are replying, as the brand {brand_name}, to a comment on its social "
        "media post. Write ONE short, warm, on-brand reply (1-2 sentences, under "
        "300 characters). Be helpful and specific to the comment. Do not use "
        "hashtags. Do not invent facts, prices, availability, or promises. If the "
        "comment asks something you can't answer, invite them to send a direct "
        "message. Never describe or make assumptions about the commenter's "
        "personal characteristics."
    )
    if persona:
        system += f" Speak in the voice of {persona}."
    context = f"Brand voice: {voice or 'friendly, professional'}\nComment: \"{comment_text}\""
    return system, context


# ---------------------------------------------------------------------------
# Token / connection helpers
# ---------------------------------------------------------------------------

async def _token_data(conn: SocialConnection) -> dict:
    data = await secrets_service.get_secret(conn.token_ref)
    if data is None:
        raise RevOSError("Token not found in secrets store.", code="token_missing", status_code=503)
    return data


_COMMENT_PLATFORMS = [
    SocialPlatform.facebook, SocialPlatform.instagram,
    SocialPlatform.youtube, SocialPlatform.threads,
]


async def _active_comment_connections(db: AsyncSession, *, account_id: uuid.UUID | None = None) -> list[SocialConnection]:
    q = select(SocialConnection).where(
        SocialConnection.platform.in_(_COMMENT_PLATFORMS),
        SocialConnection.status == SocialConnectionStatus.active,
        SocialConnection.deleted_at.is_(None),
    )
    if account_id is not None:
        q = q.where(SocialConnection.account_id == account_id)
    return list((await db.execute(q)).scalars().all())


async def _youtube_access_token(conn: SocialConnection, token_data: dict) -> str:
    """A fresh YouTube access token (refreshes + re-stores if expired). Reuses
    the connection service's refresh custody so tokens never diverge."""
    from app.services import social_connection_service
    return await social_connection_service._youtube_access_token(conn, token_data)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

async def ingest_for_connection(db: AsyncSession, conn: SocialConnection) -> int:
    """Poll one connection, store new relevant comments, draft replies. Returns
    the number of new drafts created."""
    token = await _token_data(conn)
    channel_id = str((conn.platform_meta or {}).get("channel_id", "")) if isinstance(conn.platform_meta, dict) else ""
    # Comments authored by the brand itself are skipped (don't reply to yourself).
    # Threads replies are authored by username, so include the connection's handle.
    own_ids = {
        str(token.get("page_id", "")), str(token.get("ig_user_id", "")), channel_id,
        str(conn.handle or ""),
    }

    if conn.platform == SocialPlatform.facebook:
        incoming = await meta_client.list_page_comments(token["page_id"], token["access_token"])
    elif conn.platform == SocialPlatform.instagram:
        incoming = await meta_client.list_ig_comments(token["ig_user_id"], token["access_token"])
    elif conn.platform == SocialPlatform.youtube:
        access = await _youtube_access_token(conn, token)
        incoming = await youtube_client.list_channel_comments(channel_id, access)
    elif conn.platform == SocialPlatform.threads:
        threads_user_id = token.get("threads_user_id") or conn.external_id
        incoming = await threads_client.list_replies(threads_user_id, token["access_token"])
    else:
        return 0

    cutoff = utcnow() - timedelta(hours=settings.social_comment_lookback_hours)
    drafts = 0
    for c in incoming:
        if drafts >= settings.social_comment_max_drafts_per_poll:
            break
        # Dedupe: skip anything already ingested.
        exists = await db.scalar(
            select(SocialComment.id).where(
                SocialComment.account_id == conn.account_id,
                SocialComment.external_comment_id == c.comment_id,
            )
        )
        if exists:
            continue

        posted_at = _parse_ts(c.created_time)
        if posted_at and posted_at < cutoff:
            continue

        keep, note = is_relevant(c.text, author_id=c.author_id, page_ids=own_ids)
        comment = SocialComment(
            account_id=conn.account_id,
            connection_id=conn.id,
            brand_id=conn.platform_meta.get("brand_id") if isinstance(conn.platform_meta, dict) else None,
            platform=str(conn.platform),
            external_post_id=c.post_id,
            external_comment_id=c.comment_id,
            permalink=c.permalink,
            author_name=c.author_name,
            author_external_id=c.author_id,
            text=c.text,
            posted_at=posted_at,
            relevance_note=note,
            status=SocialCommentStatus.new if keep else SocialCommentStatus.ignored,
        )
        db.add(comment)
        await db.flush()
        if keep:
            try:
                await draft_reply(db, comment)
                drafts += 1
            except Exception:  # noqa: BLE001 — one bad draft must not stop the poll
                logger.exception("Failed to draft reply for comment %s", comment.id)
    return drafts


def _parse_ts(raw: str | None):
    if not raw:
        return None
    from datetime import datetime
    try:
        # Meta uses "+0000" offset; Python needs "+00:00".
        return datetime.fromisoformat(raw.replace("+0000", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Draft
# ---------------------------------------------------------------------------

async def draft_reply(db: AsyncSession, comment: SocialComment) -> ApprovalRequest:
    brand = await db.get(Brand, comment.brand_id) if comment.brand_id else None
    voice = None
    if brand:
        bv = await brand_service.get_voice(db, brand.id)
        voice = bv.tone if bv else None
    persona = await _default_persona_voice(db, comment.account_id, comment.brand_id)

    system, context = build_reply_prompt(
        brand_name=brand.name if brand else "our brand",
        voice=voice, persona=persona, comment_text=comment.text,
    )
    text = ai_service.generate(system=system, context=context, max_tokens=180, use_case=ai_service.UC_SOCIAL)
    text = (text or "").strip().strip('"')
    if not text:
        raise RevOSError("AI drafting is not available.", code="ai_unavailable", status_code=503)

    flags = fair_housing_flags(text)
    risk = None
    if flags:
        risk = "Fair Housing review — drafted reply contained: " + ", ".join(flags) + ". Edit before approving."

    approval = ApprovalRequest(
        account_id=comment.account_id,
        brand_id=comment.brand_id,
        action_type=ApprovalAction.social_comment_reply,
        status=ApprovalStatus.pending,
        entity_type="social_comment",
        entity_id=comment.id,
        title=f"Reply to {comment.author_name or 'a commenter'} on {comment.platform.capitalize()}",
        summary=f"Comment: “{comment.text[:200]}”\n\nDrafted reply: “{text}”",
        risk_notes=risk,
        payload={
            "comment_id": str(comment.id),
            "reply_text": text,
            "comment_text": comment.text,
            "platform": comment.platform,
            "author_name": comment.author_name,
        },
    )
    db.add(approval)
    await db.flush()

    comment.drafted_reply = text
    comment.approval_id = approval.id
    comment.status = SocialCommentStatus.drafted
    db.add(comment)
    await db.flush()
    return approval


_MAX_REPLY_CHARS = 1500


async def update_draft(db: AsyncSession, comment_id: uuid.UUID, account_id: uuid.UUID, new_text: str) -> SocialComment:
    """Let a reviewer edit the drafted reply before approving. Rewrites the
    reply on both the comment and its pending ApprovalRequest, and re-runs the
    Fair Housing screen so the risk note reflects the edited text."""
    comment = await _get_comment(db, comment_id, account_id)
    if comment.status != SocialCommentStatus.drafted or not comment.approval_id:
        raise RevOSError("This comment has no editable draft.", code="not_drafted", status_code=400)

    text = (new_text or "").strip()
    if not text:
        raise RevOSError("The reply can't be empty.", code="empty_reply", status_code=400)
    if len(text) > _MAX_REPLY_CHARS:
        raise RevOSError(f"The reply must be under {_MAX_REPLY_CHARS} characters.", code="reply_too_long", status_code=400)

    approval = await db.get(ApprovalRequest, comment.approval_id)
    if approval is None or approval.status != ApprovalStatus.pending:
        raise RevOSError("The approval for this reply is no longer pending.", code="not_pending", status_code=400)

    flags = fair_housing_flags(text)
    approval.risk_notes = (
        "Fair Housing review — edited reply contains: " + ", ".join(flags) + ". Fix before approving."
        if flags else None
    )
    approval.summary = f"Comment: “{comment.text[:200]}”\n\nEdited reply: “{text}”"
    # Reassign so SQLAlchemy detects the JSON change.
    approval.payload = {**approval.payload, "reply_text": text}
    db.add(approval)

    comment.drafted_reply = text
    db.add(comment)
    await db.flush()
    return comment


async def _default_persona_voice(db, account_id, brand_id) -> str | None:
    """A consented, ready persona's voice descriptor for this brand, if any."""
    q = select(PersonaIdentity).where(
        PersonaIdentity.account_id == account_id,
        PersonaIdentity.status == PersonaIdentityStatus.ready,
        PersonaIdentity.deleted_at.is_(None),
    )
    if brand_id:
        q = q.where(PersonaIdentity.brand_id == brand_id)
    p = (await db.execute(q.limit(1))).scalars().first()
    if p is None:
        return None
    return f"{p.name} ({p.voice_notes})" if p.voice_notes else p.name


# ---------------------------------------------------------------------------
# Execute (post-approval) + like
# ---------------------------------------------------------------------------

async def execute_reply(db: AsyncSession, approval: ApprovalRequest, actor) -> None:
    """Post an approved reply. Called by the approval dispatcher; the caller
    marks the approval approved."""
    comment = await db.get(SocialComment, uuid.UUID(approval.payload["comment_id"]))
    if comment is None:
        raise NotFoundError("Comment not found.")
    conn = await db.get(SocialConnection, comment.connection_id)
    if conn is None or conn.status != SocialConnectionStatus.active:
        raise RevOSError("The connected account is no longer active.", code="connection_inactive", status_code=400)

    reply_text = approval.payload["reply_text"]
    token = await _token_data(conn)
    try:
        if comment.platform == str(SocialPlatform.facebook):
            reply_id = await meta_client.reply_to_page_comment(comment.external_comment_id, token["access_token"], reply_text)
        elif comment.platform == str(SocialPlatform.instagram):
            reply_id = await meta_client.reply_to_ig_comment(comment.external_comment_id, token["access_token"], reply_text)
        elif comment.platform == str(SocialPlatform.youtube):
            access = await _youtube_access_token(conn, token)
            reply_id = await youtube_client.reply_to_comment(comment.external_comment_id, access, reply_text)
        elif comment.platform == str(SocialPlatform.threads):
            threads_user_id = token.get("threads_user_id") or conn.external_id
            reply_id = await threads_client.reply_to_comment(
                threads_user_id, token["access_token"], comment.external_comment_id, reply_text,
            )
        else:
            raise RevOSError("Unsupported platform for comment replies.", code="unsupported", status_code=400)
    except Exception as exc:  # noqa: BLE001 — record failure on the row
        comment.status = SocialCommentStatus.failed
        comment.error = str(exc)[:2000]
        db.add(comment)
        await db.flush()
        raise

    comment.reply_external_id = reply_id
    comment.status = SocialCommentStatus.replied
    comment.error = None
    db.add(comment)
    await db.flush()


async def like_comment(db: AsyncSession, comment_id: uuid.UUID, account_id: uuid.UUID) -> SocialComment:
    comment = await _get_comment(db, comment_id, account_id)
    if comment.platform != str(SocialPlatform.facebook):
        raise RevOSError("Liking comments is only supported on Facebook.", code="like_unsupported", status_code=400)
    conn = await db.get(SocialConnection, comment.connection_id)
    if conn is None:
        raise NotFoundError("Connection not found.")
    token = await _token_data(conn)
    await meta_client.like_page_comment(comment.external_comment_id, token["access_token"])
    comment.liked = True
    db.add(comment)
    await db.flush()
    return comment


async def set_ignored(db: AsyncSession, comment_id: uuid.UUID, account_id: uuid.UUID) -> SocialComment:
    comment = await _get_comment(db, comment_id, account_id)
    comment.status = SocialCommentStatus.ignored
    # Cancel any pending approval tied to it.
    if comment.approval_id:
        appr = await db.get(ApprovalRequest, comment.approval_id)
        if appr and appr.status == ApprovalStatus.pending:
            appr.status = ApprovalStatus.cancelled
            db.add(appr)
    db.add(comment)
    await db.flush()
    return comment


async def _get_comment(db: AsyncSession, comment_id: uuid.UUID, account_id: uuid.UUID) -> SocialComment:
    result = await db.execute(
        select(SocialComment).where(
            SocialComment.id == comment_id,
            SocialComment.account_id == account_id,
            SocialComment.deleted_at.is_(None),
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise NotFoundError("Comment not found.")
    return comment


async def list_comments(db: AsyncSession, account_id: uuid.UUID, *, status: str | None = None) -> list[SocialComment]:
    q = select(SocialComment).where(
        SocialComment.account_id == account_id, SocialComment.deleted_at.is_(None),
    )
    if status:
        q = q.where(SocialComment.status == status)
    q = q.order_by(SocialComment.created_at.desc()).limit(200)
    return list((await db.execute(q)).scalars().all())


# ---------------------------------------------------------------------------
# Beat entry
# ---------------------------------------------------------------------------

async def ingest_all(db: AsyncSession) -> dict:
    """Poll every active Facebook/Instagram connection. Beat-driven."""
    if not settings.social_comment_replies_enabled:
        return {"enabled": False, "drafts": 0}
    total = 0
    conns = await _active_comment_connections(db)
    for conn in conns:
        try:
            total += await ingest_for_connection(db, conn)
            await db.commit()
        except Exception:  # noqa: BLE001 — isolate per-connection failures
            await db.rollback()
            logger.exception("Comment ingest failed for connection %s", conn.id)
    return {"enabled": True, "connections": len(conns), "drafts": total}


async def ingest_for_account(db: AsyncSession, account_id: uuid.UUID) -> dict:
    """On-demand poll for one account's own connections (the 'Sync now' button).

    Runs regardless of the global beat flag — it's an explicit admin action —
    and isolates per-connection failures so one bad token doesn't sink the rest.
    """
    total = 0
    errors = 0
    conns = await _active_comment_connections(db, account_id=account_id)
    for conn in conns:
        try:
            total += await ingest_for_connection(db, conn)
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
            errors += 1
            logger.exception("Manual comment sync failed for connection %s", conn.id)
    return {"connections": len(conns), "drafts": total, "errors": errors}

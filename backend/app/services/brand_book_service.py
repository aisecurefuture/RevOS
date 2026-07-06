"""Brand Book service (Phase 3 M1) — grounding + hallucination/compliance gate.

Two capabilities matter here:

``assemble_grounding_context`` builds the single source-of-truth block that later
generation modules inject into the prompt — brand facts, voice, approved claims,
personas, offers, and the guardrails. Generation is instructed to make factual
claims *only* from the Approved Claims section.

``check_content`` is the deterministic gate that runs on generated text before it
reaches the approval queue:
  * **Banned terms** → hard block.
  * **Required disclaimers** → flagged if missing.
  * **Numeric-claim grounding** → every claim-like number in the text (percentages,
    multipliers, money, large/formatted figures) must appear in an approved claim
    or fact; an ungrounded number is the signature of a hallucinated statistic and
    is flagged for review.

M5 layers LLM-based semantic verification on top of this; the interface is stable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundError
from app.models.base import utcnow
from app.models.brand import Brand, BrandVoice, BuyerPersona
from app.models.brand_book import BrandBook, BrandClaim, BrandFact
from app.models.offer import Offer, OfferStatus
from app.models.user import AdminUser
from app.services import ai_service

logger = logging.getLogger("revos.brand_book")


# ---------------------------------------------------------------------------
# Numeric-claim extraction (the hallucination heuristic)
# ---------------------------------------------------------------------------

_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
_NUM_RE = re.compile(
    r"(?P<money>\$)?"
    r"(?P<num>\d[\d,]*(?:\.\d+)?)"
    r"\s*(?P<mult>k|m|b|thousand|million|billion)?"
    r"(?P<unit>%|x)?",
    re.IGNORECASE,
)


def _extract_claim_numbers(text: str) -> set[tuple[float, str]]:
    """Extract *claim-like* numbers as (canonical_value, type) pairs, where type
    is one of '', '%', 'x', '$'. Plain small integers, list counts, and 4-digit
    years are ignored to keep the false-positive rate low."""
    out: set[tuple[float, str]] = set()
    for m in _NUM_RE.finditer(text):
        raw = m.group("num")
        if not raw or not any(c.isdigit() for c in raw):
            continue
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        mult = (m.group("mult") or "").lower()
        unit = (m.group("unit") or "").lower()
        money = bool(m.group("money"))
        value *= _MULT.get(mult, 1.0)

        if unit == "%":
            typ = "%"
        elif unit == "x":
            typ = "x"
        elif money:
            typ = "$"
        else:
            typ = ""

        claim_like = bool(unit or money or mult)
        if not claim_like:
            # A bare number counts only if it's large and not obviously a year.
            if value < 1000:
                continue
            if 1900 <= value <= 2100 and value == int(value):
                continue
        out.add((round(value, 4), typ))
    return out


# ---------------------------------------------------------------------------
# Grounding pack + content check result
# ---------------------------------------------------------------------------

@dataclass
class GroundingPack:
    prompt_context: str
    banned_terms: list[str] = field(default_factory=list)
    required_disclaimers: list[str] = field(default_factory=list)
    approved_claims: list[str] = field(default_factory=list)
    is_published: bool = False


@dataclass
class ContentCheck:
    passed: bool               # clean — safe for hands-off auto-approve
    blocked: bool              # hard violation (banned term) — must never auto-publish
    banned_hits: list[str] = field(default_factory=list)
    missing_disclaimers: list[str] = field(default_factory=list)
    unverified_numbers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def get_or_create_book(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID) -> BrandBook:
    result = await db.execute(
        select(BrandBook).where(BrandBook.brand_id == brand_id, BrandBook.deleted_at.is_(None))
    )
    book = result.scalar_one_or_none()
    if book is None:
        book = BrandBook(account_id=account_id, brand_id=brand_id)
        db.add(book)
        await db.flush()
        await db.refresh(book)
    return book


async def update_book(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID, data: dict) -> BrandBook:
    book = await get_or_create_book(db, brand_id, account_id)
    for key, value in data.items():
        setattr(book, key, value)
    db.add(book)
    await db.flush()
    await db.refresh(book)
    return book


async def list_claims(db: AsyncSession, brand_id: uuid.UUID) -> list[BrandClaim]:
    result = await db.execute(
        select(BrandClaim).where(
            BrandClaim.brand_id == brand_id, BrandClaim.deleted_at.is_(None)
        ).order_by(BrandClaim.created_at.desc())
    )
    return list(result.scalars().all())


async def create_claim(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID, user: AdminUser, data: dict) -> BrandClaim:
    claim = BrandClaim(account_id=account_id, brand_id=brand_id, created_by=user.id, **data)
    db.add(claim)
    await db.flush()
    await db.refresh(claim)
    return claim


async def delete_claim(db: AsyncSession, claim_id: uuid.UUID, brand_id: uuid.UUID) -> None:
    result = await db.execute(
        select(BrandClaim).where(BrandClaim.id == claim_id, BrandClaim.brand_id == brand_id)
    )
    claim = result.scalar_one_or_none()
    if claim is None:
        raise NotFoundError("Claim not found.")
    claim.deleted_at = utcnow()
    db.add(claim)
    await db.flush()


async def list_facts(db: AsyncSession, brand_id: uuid.UUID) -> list[BrandFact]:
    result = await db.execute(
        select(BrandFact).where(
            BrandFact.brand_id == brand_id, BrandFact.deleted_at.is_(None)
        ).order_by(BrandFact.created_at.desc())
    )
    return list(result.scalars().all())


async def create_fact(db: AsyncSession, brand_id: uuid.UUID, account_id: uuid.UUID, user: AdminUser, data: dict) -> BrandFact:
    fact = BrandFact(account_id=account_id, brand_id=brand_id, created_by=user.id, **data)
    db.add(fact)
    await db.flush()
    await db.refresh(fact)
    return fact


async def delete_fact(db: AsyncSession, fact_id: uuid.UUID, brand_id: uuid.UUID) -> None:
    result = await db.execute(
        select(BrandFact).where(BrandFact.id == fact_id, BrandFact.brand_id == brand_id)
    )
    fact = result.scalar_one_or_none()
    if fact is None:
        raise NotFoundError("Fact not found.")
    fact.deleted_at = utcnow()
    db.add(fact)
    await db.flush()


# ---------------------------------------------------------------------------
# Approved-claim gathering (shared by grounding + checking)
# ---------------------------------------------------------------------------

async def _approved_claims(db: AsyncSession, brand_id: uuid.UUID) -> list[BrandClaim]:
    now = utcnow()
    claims = await list_claims(db, brand_id)
    return [c for c in claims if c.approved and (c.expires_at is None or c.expires_at > now)]


# ---------------------------------------------------------------------------
# Grounding context assembly
# ---------------------------------------------------------------------------

async def assemble_grounding_context(db: AsyncSession, brand_id: uuid.UUID) -> GroundingPack:
    """Build the source-of-truth block injected into generation prompts."""
    brand = await db.get(Brand, brand_id)
    if brand is None:
        raise NotFoundError("Brand not found.")

    book_res = await db.execute(select(BrandBook).where(BrandBook.brand_id == brand_id, BrandBook.deleted_at.is_(None)))
    book = book_res.scalar_one_or_none()
    voice_res = await db.execute(select(BrandVoice).where(BrandVoice.brand_id == brand_id, BrandVoice.deleted_at.is_(None)))
    voice = voice_res.scalar_one_or_none()
    personas_res = await db.execute(select(BuyerPersona).where(BuyerPersona.brand_id == brand_id, BuyerPersona.deleted_at.is_(None)))
    personas = list(personas_res.scalars().all())
    offers_res = await db.execute(
        select(Offer).where(
            Offer.brand_id == brand_id, Offer.deleted_at.is_(None), Offer.status == OfferStatus.active
        )
    )
    offers = list(offers_res.scalars().all())
    claims = await _approved_claims(db, brand_id)
    facts = await list_facts(db, brand_id)

    lines: list[str] = [f"# Brand: {brand.name}"]
    if brand.tagline:
        lines.append(f"Tagline: {brand.tagline}")
    if brand.description:
        lines.append(f"Description: {brand.description}")

    if book:
        if book.mission:
            lines.append(f"\n## Mission\n{book.mission}")
        if book.vision:
            lines.append(f"\n## Vision (long-term outcome if the mission succeeds)\n{book.vision}")
        if book.positioning:
            lines.append(f"\n## Positioning\n{book.positioning}")
        if book.elevator_pitch:
            lines.append(f"\n## Elevator pitch\n{book.elevator_pitch}")
        if book.key_messages:
            lines.append("\n## Key messages\n" + "\n".join(f"- {m}" for m in book.key_messages))
        if book.target_summary:
            lines.append(f"\n## Target customer\n{book.target_summary}")
        if book.audience_exclusions:
            lines.append(f"\n## Who this is NOT for\n{book.audience_exclusions}")
        if book.core_values:
            cv_lines = []
            for cv in book.core_values:
                bit = f"- **{cv.get('value')}**"
                if cv.get("statement"):
                    bit += f": {cv['statement']}"
                if cv.get("example"):
                    bit += f" (e.g. {cv['example']})"
                cv_lines.append(bit)
            lines.append("\n## Core values\n" + "\n".join(cv_lines))
        if book.brand_story:
            lines.append(f"\n## Brand story (draw on this for authentic, personal narrative content)\n{book.brand_story}")

    if voice or (book and (book.brand_archetype or book.voice_spectrum)):
        v: list[str] = []
        if voice and voice.tone:
            v.append(f"Tone: {voice.tone}")
        if voice and voice.style_notes:
            v.append(f"Style: {voice.style_notes}")
        if book and book.brand_archetype:
            v.append(f"Brand archetype: {book.brand_archetype}")
        if book and book.voice_spectrum:
            spectrum_labels = {
                "humor": ("funny", "serious"),
                "energy": ("matter-of-fact", "enthusiastic"),
                "formality": ("formal", "casual"),
                "convention": ("conventional", "quirky"),
            }
            s_bits = []
            for key, (lo, hi) in spectrum_labels.items():
                if key in book.voice_spectrum:
                    s_bits.append(f"{key}={book.voice_spectrum[key]}/5 ({lo}→{hi})")
            if s_bits:
                v.append("Voice spectrum: " + ", ".join(s_bits))
        if voice and voice.value_props:
            v.append("Value props: " + "; ".join(voice.value_props))
        if voice and voice.vocabulary:
            v.append("Preferred vocabulary: " + ", ".join(voice.vocabulary))
        if voice and voice.do_list:
            v.append("Do: " + "; ".join(voice.do_list))
        if voice and voice.dont_list:
            v.append("Don't: " + "; ".join(voice.dont_list))
        if v:
            lines.append("\n## Voice & style\n" + "\n".join(v))

    if personas:
        p_lines = []
        for p in personas:
            bits = [f"- **{p.name}**" + (f" ({p.role_title})" if p.role_title else "")]
            if p.summary:
                bits.append(f": {p.summary}")
            if p.pain_points:
                bits.append(" Pains: " + "; ".join(p.pain_points))
            p_lines.append("".join(bits))
        lines.append("\n## Audience personas\n" + "\n".join(p_lines))

    if offers:
        o_lines = []
        for o in offers:
            price = f" (${o.price_cents / 100:.0f})" if o.price_cents else ""
            o_lines.append(f"- {o.name}{price}" + (f": {o.subtitle or o.description or ''}").rstrip(": "))
        lines.append("\n## Offers\n" + "\n".join(o_lines))

    claim_strings = [c.claim for c in claims]
    if claims:
        c_lines = []
        for c in claims:
            c_lines.append(f"- {c.claim}" + (f"  _(proof: {c.proof})_" if c.proof else ""))
        lines.append(
            "\n## Approved claims (the ONLY factual claims you may make)\n"
            + "\n".join(c_lines)
        )
    else:
        lines.append(
            "\n## Approved claims\n(None on file — do NOT state any specific "
            "statistics, metrics, certifications, or awards.)"
        )

    if facts:
        f_lines = [f"- **{f.topic}**: {f.content}" for f in facts]
        lines.append("\n## Knowledge base\n" + "\n".join(f_lines))

    banned = list(book.banned_terms) if book else []
    disclaimers = list(book.required_disclaimers) if book else []

    guard = ["\n## Guardrails (must follow)"]
    guard.append("- Make factual claims ONLY from the Approved claims above. Never invent statistics, metrics, numbers, certifications, or awards.")
    if book and book.compliance_notes:
        guard.append(f"- {book.compliance_notes}")
    if book and book.competitors:
        guard.append("- Do not disparage or name competitors: " + ", ".join(book.competitors))
    if banned:
        guard.append("- Never use these terms: " + ", ".join(banned))
    if disclaimers:
        guard.append("- Include these disclaimers verbatim where relevant: " + " | ".join(disclaimers))
    lines.append("\n".join(guard))

    return GroundingPack(
        prompt_context="\n".join(lines),
        banned_terms=banned,
        required_disclaimers=disclaimers,
        approved_claims=claim_strings,
        is_published=bool(book and book.is_published),
    )


# ---------------------------------------------------------------------------
# Content check (the gate)
# ---------------------------------------------------------------------------

async def check_content(
    db: AsyncSession, brand_id: uuid.UUID, text: str, *, require_disclaimers: bool = False
) -> ContentCheck:
    """Deterministic hallucination / compliance gate for generated ``text``."""
    book_res = await db.execute(select(BrandBook).where(BrandBook.brand_id == brand_id, BrandBook.deleted_at.is_(None)))
    book = book_res.scalar_one_or_none()
    banned = [t for t in (book.banned_terms if book else [])]
    disclaimers = [d for d in (book.required_disclaimers if book else [])]

    lower = text.lower()

    banned_hits = [t for t in banned if t.strip() and t.lower() in lower]

    missing_disclaimers = []
    if require_disclaimers:
        missing_disclaimers = [d for d in disclaimers if d.strip() and d.lower() not in lower]

    # Numeric-claim grounding.
    claims = await _approved_claims(db, brand_id)
    facts = await list_facts(db, brand_id)
    grounded_text = " ".join(
        [c.claim for c in claims] + [c.proof or "" for c in claims] + [f.content for f in facts]
    )
    grounded_numbers = _extract_claim_numbers(grounded_text)
    text_numbers = _extract_claim_numbers(text)
    ungrounded = text_numbers - grounded_numbers

    def _fmt(n: tuple[float, str]) -> str:
        value, typ = n
        v = int(value) if value == int(value) else value
        return f"{v}{typ}"

    unverified = sorted(_fmt(n) for n in ungrounded)

    blocked = bool(banned_hits)
    passed = not blocked and not missing_disclaimers and not unverified
    return ContentCheck(
        passed=passed,
        blocked=blocked,
        banned_hits=banned_hits,
        missing_disclaimers=missing_disclaimers,
        unverified_numbers=unverified,
    )


# ---------------------------------------------------------------------------
# M5 — LLM claim verification (semantic layer on top of the deterministic gate)
# ---------------------------------------------------------------------------

@dataclass
class LlmVerification:
    ok: bool                                    # True only if the verifier ran AND parsed
    unsupported_claims: list[str] = field(default_factory=list)
    error: str | None = None                    # reason it couldn't verify


@dataclass
class VerificationResult:
    """Combined gate: the deterministic check plus the optional LLM claim check.

    ``passed`` is the safe-for-hands-off verdict — clean on EVERY layer that
    ran. It fails closed: if the LLM check was requested and could not run, the
    content is NOT considered passed.
    """
    passed: bool
    blocked: bool
    deterministic: ContentCheck
    llm_checked: bool = False
    unsupported_claims: list[str] = field(default_factory=list)
    llm_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "banned_hits": self.deterministic.banned_hits,
            "unverified_numbers": self.deterministic.unverified_numbers,
            "missing_disclaimers": self.deterministic.missing_disclaimers,
            "llm_checked": self.llm_checked,
            "unsupported_claims": self.unsupported_claims,
            "llm_error": self.llm_error,
        }


_VERIFIER_SYSTEM = (
    "You are a strict fact-checker for marketing content. You are given the COMPLETE set "
    "of facts a brand is permitted to assert, and a piece of content. Find every FACTUAL "
    "CLAIM in the content that is not directly supported by those facts. A factual claim "
    "states something as objective truth: a capability, feature, statistic, certification, "
    "award, partnership, comparison, guarantee, or specific outcome. Calls to action, "
    "opinions, questions, and general encouragement are NOT factual claims. Be strict — if "
    "a claim is not clearly supported by the permitted facts, list it verbatim. Respond with "
    'ONLY a JSON object and nothing else: {"unsupported_claims": ["<claim>", ...]}. If every '
    'factual claim is supported (or there are none), respond {"unsupported_claims": []}.'
)


def _parse_verdict(raw: str) -> list[str] | None:
    """Extract the unsupported_claims list from the model's response, tolerating
    markdown fences / preamble. Returns None if it can't be parsed (fail closed)."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    claims = data.get("unsupported_claims")
    if not isinstance(claims, list):
        return None
    return [str(c).strip() for c in claims if str(c).strip()][:25]


async def verify_claims_llm(*, approved: list[str], facts: list[str], content: str) -> LlmVerification:
    """LLM claim check. Fails closed: any inability to verify → ok=False."""
    if not ai_service.ai_available():
        return LlmVerification(ok=False, error="no_provider")

    source_parts = []
    if approved:
        source_parts.append("Approved claims:\n" + "\n".join(f"- {c}" for c in approved))
    if facts:
        source_parts.append("Known facts:\n" + "\n".join(f"- {f}" for f in facts))
    source = "\n\n".join(source_parts) or "(no approved claims or facts on file)"
    context = f"PERMITTED FACTS:\n{source}\n\nCONTENT TO CHECK:\n{content}"

    raw = await asyncio.to_thread(
        ai_service.analyze, system=_VERIFIER_SYSTEM, context=context,
        max_tokens=600, use_case="summary",
    )
    if not raw:
        return LlmVerification(ok=False, error="generation_failed")
    parsed = _parse_verdict(raw)
    if parsed is None:
        logger.warning("Claim verifier returned unparseable output: %s", raw[:300])
        return LlmVerification(ok=False, error="unparseable")
    return LlmVerification(ok=True, unsupported_claims=parsed)


async def verify_content(
    db: AsyncSession, brand_id: uuid.UUID, text: str, *,
    require_disclaimers: bool = False, use_llm: bool | None = None,
) -> VerificationResult:
    """Full gate = deterministic check + (optional) LLM claim verification.

    ``use_llm`` overrides the ``LLM_CLAIM_VERIFICATION`` setting. When the LLM
    check runs but cannot complete (call/parse failure), the result fails closed
    (passed=False). When no AI provider exists at all, it degrades to
    deterministic-only (there's no LLM to verify with, and no LLM to have
    generated the content either)."""
    det = await check_content(db, brand_id, text, require_disclaimers=require_disclaimers)

    run_llm = settings.llm_claim_verification if use_llm is None else use_llm
    if not run_llm or not ai_service.ai_available():
        return VerificationResult(
            passed=det.passed, blocked=det.blocked, deterministic=det, llm_checked=False,
        )

    claims = await _approved_claims(db, brand_id)
    facts = await list_facts(db, brand_id)
    llm = await verify_claims_llm(
        approved=[c.claim for c in claims],
        facts=[f"{f.topic}: {f.content}" for f in facts],
        content=text,
    )
    if not llm.ok:
        # Requested + provider available, but verification failed → fail closed.
        return VerificationResult(
            passed=False, blocked=det.blocked, deterministic=det,
            llm_checked=False, llm_error=llm.error,
        )

    passed = det.passed and not llm.unsupported_claims
    return VerificationResult(
        passed=passed, blocked=det.blocked, deterministic=det,
        llm_checked=True, unsupported_claims=llm.unsupported_claims,
    )

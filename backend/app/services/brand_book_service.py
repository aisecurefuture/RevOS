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

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.base import utcnow
from app.models.brand import Brand, BrandVoice, BuyerPersona
from app.models.brand_book import BrandBook, BrandClaim, BrandFact
from app.models.offer import Offer, OfferStatus
from app.models.user import AdminUser


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
        if book.positioning:
            lines.append(f"\n## Positioning\n{book.positioning}")
        if book.elevator_pitch:
            lines.append(f"\n## Elevator pitch\n{book.elevator_pitch}")
        if book.key_messages:
            lines.append("\n## Key messages\n" + "\n".join(f"- {m}" for m in book.key_messages))
        if book.target_summary:
            lines.append(f"\n## Target customer\n{book.target_summary}")

    if voice:
        v: list[str] = []
        if voice.tone:
            v.append(f"Tone: {voice.tone}")
        if voice.style_notes:
            v.append(f"Style: {voice.style_notes}")
        if voice.value_props:
            v.append("Value props: " + "; ".join(voice.value_props))
        if voice.vocabulary:
            v.append("Preferred vocabulary: " + ", ".join(voice.vocabulary))
        if voice.do_list:
            v.append("Do: " + "; ".join(voice.do_list))
        if voice.dont_list:
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

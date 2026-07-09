"""PowerPoint → Deck Spec draft (Pitch Video Studio).

Turns an uploaded .pptx into a DRAFT Deck Spec the user reviews and edits in
the studio textarea before rendering — slide→scene mapping and narration
writing are judgment calls, so this never goes straight to render.

Two tiers:
  * AI-assisted (when an AI provider is configured): slide text +
    the scene-layout catalog go to ai_service.generate, which drafts layouts,
    condensed on-screen content, and TTS-phonetic narration. The draft is
    validated against the real Deck Spec schema; anything unparseable or
    invalid falls back to the deterministic tier rather than erroring.
  * Deterministic: title slide → hero, last slide → close, everything else →
    statement scenes with the slide's text; narration = the on-screen text.
    Crude but always works, and the user edits from there.

Extraction is stdlib-only (a .pptx is a zip of XML) — no python-pptx dep.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import zipfile
from xml.etree import ElementTree

from app.core.exceptions import RevOSError
from app.services import ai_service

logger = logging.getLogger("revos.pptx_import")

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
_MAX_SLIDES = 40
_MAX_PPTX_BYTES = 50 * 1024 * 1024


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_slides(data: bytes) -> list[dict]:
    """Parse a .pptx into [{"index", "title", "body": [str, ...]}, ...]."""
    if len(data) > _MAX_PPTX_BYTES:
        raise RevOSError("PowerPoint file is too large (max 50MB).", code="file_too_large", status_code=400)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        slide_names = sorted(
            (n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
            key=lambda n: int(re.search(r"\d+", n).group()),  # type: ignore[union-attr]
        )
    except zipfile.BadZipFile as exc:
        raise RevOSError("That file isn't a valid .pptx.", code="invalid_pptx", status_code=400) from exc
    if not slide_names:
        raise RevOSError("No slides found in this file.", code="empty_pptx", status_code=400)

    slides = []
    for i, name in enumerate(slide_names[:_MAX_SLIDES], start=1):
        try:
            root = ElementTree.fromstring(archive.read(name))
        except ElementTree.ParseError:
            logger.warning("Skipping unparseable slide %s", name)
            continue
        title_parts: list[str] = []
        body_parts: list[str] = []
        for shape in root.iter(f"{{{_NS['p']}}}sp"):
            ph = shape.find(f".//{{{_NS['p']}}}ph")
            # Slide-number / footer / date placeholders are chrome, not content
            # — leaking them into narration produces junk like
            # "acme · confidential · 2" being read aloud.
            if ph is not None and ph.get("type") in ("sldNum", "ftr", "dt"):
                continue
            is_title = ph is not None and ph.get("type") in ("title", "ctrTitle")
            # One string per paragraph, joining that paragraph's text runs.
            for para in shape.iter(f"{{{_NS['a']}}}p"):
                text = "".join(t.text or "" for t in para.iter(f"{{{_NS['a']}}}t")).strip()
                if not text:
                    continue
                (title_parts if is_title else body_parts).append(text)
        slides.append({
            "index": i,
            "title": " ".join(title_parts) or None,
            "body": body_parts,
        })
    if not any(s["title"] or s["body"] for s in slides):
        raise RevOSError(
            "Couldn't extract any text from this file (image-only slides?).",
            code="no_text", status_code=400,
        )
    return slides


# ---------------------------------------------------------------------------
# Deterministic draft
# ---------------------------------------------------------------------------

def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def deterministic_scene(slide: dict, position: int, last: int) -> dict:
    """The always-valid mechanical scene for one slide (also the per-scene
    fallback when AI drafting fails for that slide alone)."""
    title = slide["title"] or (slide["body"][0] if slide["body"] else f"Slide {slide['index']}")
    body = [b for b in slide["body"] if b != title]
    # Join fragments with sentence enders — slide bullets carry no
    # punctuation, and TTS needs split points (XTTS hard-fails on one
    # long unbreakable chunk). Cap at ~600 chars (~40s spoken): a scene,
    # not a lecture — the user edits the draft anyway.
    narration = _clip(
        " ".join(f"{part.rstrip('.!?…')}." for part in [title, *body] if part.strip()) or f"{title}.",
        600,
    )
    if position == 0:
        return {
            "id": f"slide-{slide['index']}", "layout": "hero", "variant": "dark",
            "content": {"headline": _clip(title, 290), "sub": _clip(body[0], 490) if body else None},
            "narration": narration,
        }
    if position == last:
        return {
            "id": f"slide-{slide['index']}", "layout": "close", "variant": "dark",
            "content": {"headline": _clip(title, 290), "sub": _clip(body[0], 490) if body else None},
            "narration": narration,
        }
    return {
        "id": f"slide-{slide['index']}", "layout": "statement", "variant": "light",
        "content": {"text": _clip(title, 490)},
        "narration": narration,
    }


def _capped(slides: list[dict]) -> list[dict]:
    from app.config import settings

    # Respect the deck-size cap: keep the first N-1 slides + the closing slide.
    cap = settings.pitch_video_max_scenes
    if len(slides) > cap:
        return slides[: cap - 1] + [slides[-1]]
    return slides


def deterministic_draft(slides: list[dict], brand_slug: str) -> dict:
    slides = _capped(slides)
    last = len(slides) - 1
    scenes = [deterministic_scene(s, i, last) for i, s in enumerate(slides)]
    return {
        "brandId": brand_slug,
        "title": slides[0]["title"] or "Imported deck",
        "aspectRatio": "16:9",
        "voice": "",
        "scenes": scenes,
    }


# ---------------------------------------------------------------------------
# AI-assisted draft
# ---------------------------------------------------------------------------

_DRAFT_SYSTEM = """You convert slide-deck text into a Deck Spec JSON for a narrated pitch video.

Output ONLY a JSON object, no markdown fences or commentary, with this shape:
{"brandId": "<given>", "title": "<deck title>", "aspectRatio": "16:9", "voice": "",
 "style": "<given>",
 "scenes": [{"id": "<unique-slug>", "layout": "<layout>", "variant": "light"|"dark",
             "content": {...}, "narration": "<spoken text>"}]}

Layouts and their exact content shapes:
- hero: {"eyebrow"?: str, "headline": str, "sub"?: str} — openers
- statement: {"text": str, "equation"?: [str, ...]} — one bold idea
- stat-trio: {"stats": [{"value": str, "label": str}]} — 1 stat renders as a
  drawn risk-curve composition, 2-4 as big-number cards
- two-column: {"left": {"heading","body"}, "right": {"heading","body"}} — contrast
- architecture: {"bands": [{"label", "description"?}]} — layered how-it-works
- bar-chart: {"bars": [{"category", "segments": [{"label","value":number}]}], "note"?: str} — trends/financials
- timeline: {"steps": [{"label", "description"?}]} — phases/roadmap
- team: {"members": [{"name","role","bio"?}]} — people
- close: {"headline", "sub"?} — final CTA
- split-reveal: {"left": {"label", "lines": [{"text","highlight"?:bool}]},
  "right": {...same}, "caption"?: str} — two schematic cards side by side
  (before/after, seen-vs-hidden, checklist-vs-score; "" text = skeleton bar)
- verdict-lanes: {"lanes": [str, ...], "caption"?: str} — 2-6 outcome lanes
- card-grid: {"cards": [{"title","value","open"?:bool}], "caption"?, "note"?} —
  a dealt grid of value cards; open=true = the dashed "unclaimed" slot
- stack-summary: {"blocks": [{"label","value"}], "summary_label", "summary_big",
  "capline"?, "note"?} — building blocks + a summary card (business models,
  revenue plans). If the summary shows a projection/valuation, "note" MUST
  carry the slide's illustrative/disclaimer language — it renders in the same
  frame as the figure.
- terms: {"label", "big", "sub"?, "chips": [str]} — a deal/ask card + milestone chips

Optional per-scene fields (use them when style is "schematic"):
- "chapter": {"num": "1", "label": "THE STAKES"} — group scenes into 3-5
  chapters after the cold-open; the label is 1-3 words, uppercase.
- "emphasis": exact substring of the headline/caption that deserves the
  luminous underline (ONE per scene, the single most quotable phrase).
- "motif": "stream" or "gate" on hero scenes only — adds an animated
  content-stream / scanning-gate backdrop.

Rules:
- One scene per meaningful slide; merge thin slides, skip agenda/blank ones. 6-14 scenes.
- Condense on-screen text hard — a video frame holds far less than a slide.
- narration: 30-45 spoken words per scene, ~150wpm pacing, conversational,
  written PHONETICALLY for text-to-speech: "A-I" not "AI", "U-R-L" not "URL",
  "example dot com" for domains, numbers spelled out ("fifteen million dollars").
- If a slide shows financial projections, keep any illustrative/disclaimer
  framing from the slide in both the content note and the narration.
- style "minimal": use dark variant for openers/stats/closers, light for
  explanatory scenes. style "schematic": prefer dark everywhere, open on a
  hero (motif "stream" if the deck is about data/content flows), and shape
  the arc hook → stakes → fix → proof → ask → close."""


def _parse_draft(raw: str) -> dict | None:
    """Extract the first complete JSON object from model output.

    Local models decorate JSON with reasoning blocks, markdown fences, and
    trailing chatter — and sometimes truncate mid-object. Strip the noise,
    then raw_decode from the first '{' (immune to anything after the object,
    unlike a greedy first-{…last-} regex). Truncated JSON still returns None
    — the caller falls back."""
    cleaned = re.sub(r"<think>.*?(?:</think>|$)", "", raw, flags=re.DOTALL)
    cleaned = cleaned.replace("```json", "```")
    start = cleaned.find("{")
    while start != -1:
        try:
            data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        except ValueError:
            start = cleaned.find("{", start + 1)
            continue
        return data if isinstance(data, dict) else None
    return None


# Per-scene prompt for the fallback path: ONE slide → ONE scene object.
# Small local models fail one-shot whole-deck JSON far more often than a
# single small object; this path trades one big call for N small ones.
_DRAFT_SCENE_SYSTEM = """You convert ONE slide's text into ONE scene JSON object for a narrated pitch video.

Output ONLY the JSON object — no markdown fences, no commentary, no reasoning:
{"id": "<slug>", "layout": "<layout>", "variant": "light"|"dark",
 "content": {...}, "narration": "<spoken text>"}

Pick the best layout for this slide and use its exact content shape:
- hero: {"eyebrow"?: str, "headline": str, "sub"?: str}
- statement: {"text": str}
- stat-trio: {"stats": [{"value": str, "label": str}]} (1-4 stats)
- two-column: {"left": {"heading","body"}, "right": {"heading","body"}}
- architecture: {"bands": [{"label", "description"?}]}
- bar-chart: {"bars": [{"category", "segments": [{"label","value":number}]}], "note"?: str}
- timeline: {"steps": [{"label", "description"?}]}
- team: {"members": [{"name","role","bio"?}]}
- card-grid: {"cards": [{"title","value"}], "caption"?, "note"?}
- terms: {"label", "big", "sub"?, "chips": [str]}
- close: {"headline", "sub"?}

Rules:
- Condense on-screen text hard; narration is 30-45 conversational spoken words,
  written PHONETICALLY for text-to-speech ("A-I" not "AI", "example dot com",
  numbers spelled out).
- Keep any illustrative/disclaimer language from financial slides in both the
  note and the narration."""


def _slide_block(s: dict) -> str:
    return f"SLIDE {s['index']}: {s['title'] or '(no title)'}\n" + "\n".join(f"- {b}" for b in s["body"])


async def _draft_scene_by_scene(
    slides: list[dict], style: str,
) -> tuple[list[dict], list[bool]]:
    """One small AI call per slide; any slide that fails gets its
    deterministic scene. Returns (scenes, per-scene ai flags)."""
    last = len(slides) - 1
    scenes: list[dict] = []
    ai_flags: list[bool] = []
    for i, slide in enumerate(slides):
        fallback = deterministic_scene(slide, i, last)
        position = "the opening slide" if i == 0 else ("the closing slide" if i == last else f"slide {i + 1} of {last + 1}")
        raw = await asyncio.to_thread(
            ai_service.generate, system=_DRAFT_SCENE_SYSTEM,
            context=f"style: {style} · this is {position}\n\n{_slide_block(slide)}",
            max_tokens=1200, use_case="social",
        )
        scene = _parse_draft(raw) if raw else None
        if scene is None or "layout" not in scene or "narration" not in scene:
            scenes.append(fallback)
            ai_flags.append(False)
            continue
        scene["id"] = fallback["id"]  # stable, unique ids from slide numbers
        scene.setdefault("variant", "dark" if style == "schematic" else fallback["variant"])
        scene.setdefault("content", {})
        scenes.append(scene)
        ai_flags.append(True)
    return scenes, ai_flags


async def draft_deck_spec(
    slides: list[dict], brand_slug: str, style: str = "minimal",
) -> tuple[dict, bool]:
    """Returns (draft, ai_drafted). Always yields a schema-valid draft.

    Strategy ladder: one-shot whole-deck AI draft → scene-by-scene AI drafting
    (small models produce one valid small object far more reliably than one
    big document; failed scenes degrade individually) → fully deterministic."""
    from app.services.pitch_video_service import validate_deck_spec

    slides = _capped(slides)
    deterministic = {**deterministic_draft(slides, brand_slug), "style": style}
    validate_deck_spec({**deterministic, "voice": "x"})  # invariant: fallback is always valid

    if not ai_service.ai_available():
        return deterministic, False

    slide_text = "\n\n".join(_slide_block(s) for s in slides)
    context = f"brandId to use: {brand_slug}\nstyle to use: {style}\n\n{slide_text}"
    raw = await asyncio.to_thread(
        ai_service.generate, system=_DRAFT_SYSTEM, context=context,
        max_tokens=8000, use_case="social",
    )
    draft = _parse_draft(raw) if raw else None
    if draft is None:
        logger.warning(
            "PPTX one-shot AI draft unparseable (head: %r); trying scene-by-scene.",
            (raw or "")[:300],
        )
        return await _try_scene_by_scene(slides, brand_slug, style, deterministic)
    draft["brandId"] = brand_slug  # never trust the model with tenant routing
    draft["style"] = style          # the user's choice, not the model's
    try:
        validate_deck_spec({**draft, "voice": draft.get("voice") or "x"})
    except RevOSError as exc:
        logger.warning(
            "PPTX one-shot AI draft failed schema validation (%s); trying scene-by-scene.",
            exc.message,
        )
        return await _try_scene_by_scene(slides, brand_slug, style, deterministic)
    return draft, True


async def _try_scene_by_scene(
    slides: list[dict], brand_slug: str, style: str, deterministic: dict,
) -> tuple[dict, bool]:
    from app.services.pitch_video_service import validate_deck_spec

    scenes, ai_flags = await _draft_scene_by_scene(slides, style)
    draft = {**deterministic, "scenes": scenes}
    # Validate each AI scene; swap any invalid one for its deterministic twin
    # rather than discarding the whole draft.
    for i, scene in enumerate(scenes):
        if not ai_flags[i]:
            continue
        try:
            validate_deck_spec({**draft, "voice": "x", "scenes": [scene]})
        except RevOSError:
            scenes[i] = deterministic_scene(slides[i], i, len(slides) - 1)
            ai_flags[i] = False
    validate_deck_spec({**draft, "voice": "x"})  # belt-and-braces on the assembly
    ai_count = sum(ai_flags)
    ai_drafted = ai_count > 0
    if ai_drafted:
        logger.info("PPTX scene-by-scene drafting: %d/%d scenes AI-drafted.", ai_count, len(scenes))
    else:
        logger.warning("PPTX scene-by-scene drafting produced nothing usable; deterministic draft.")
    return draft, ai_drafted

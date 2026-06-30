"""Text helpers: slugify and plain-text cleaning (XSS defense in depth)."""

from __future__ import annotations

import re

from app.core.sanitize import strip_all

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, hyphenated, ASCII slug derived from arbitrary text."""
    cleaned = strip_all(value).lower().strip()
    slug = _SLUG_RE.sub("-", cleaned).strip("-")
    return slug[:120] or "item"


def clean_text(value: str | None) -> str | None:
    """Strip any HTML tags from a plain-text field and trim whitespace."""
    if value is None:
        return None
    return strip_all(value).strip() or None

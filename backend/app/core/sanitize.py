"""HTML sanitization (XSS defense).

User-authored HTML (landing-page bodies, content, email templates) is sanitized
with an allowlist before it is stored/rendered. Plain-text fields are stripped
of all markup.
"""

from __future__ import annotations

import bleach

# Conservative rich-text allowlist for marketing content.
ALLOWED_TAGS = [
    "a", "b", "strong", "i", "em", "u", "p", "br", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "code", "pre",
    "span", "div", "img", "hr", "table", "thead", "tbody", "tr", "th", "td",
]
ALLOWED_ATTRS = {
    # `target` is intentionally NOT allowed — it enables reverse-tabnabbing and
    # forced a fragile post-hoc rel=noopener patch. Links open in the same tab.
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "span": ["class"],
    "div": ["class"],
}
# Note: inline `style` is intentionally NOT allowed — without a CSS sanitizer
# bleach strips it anyway, and it is an XSS vector in legacy engines.
# Only safe URL schemes; blocks javascript:, data: (except images handled below).
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def sanitize_html(html: str | None) -> str:
    """Return XSS-safe HTML using the allowlist. Links open same-tab (no
    target), so reverse-tabnabbing is structurally impossible."""
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )


def strip_all(text: str | None) -> str:
    """Remove every tag — for fields that must be plain text."""
    if not text:
        return ""
    return bleach.clean(text, tags=[], attributes={}, strip=True)

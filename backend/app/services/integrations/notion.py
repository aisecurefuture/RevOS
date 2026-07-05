"""Notion API — push CRM contacts into a customer's database — Phase 3.

We don't assume the customer's database schema matches ours, so we fetch it
first and only populate properties that (a) exist and (b) have a type we know
how to fill. Extra required properties in their database that we don't
recognize are left for the customer to fill in manually — Notion still creates
the page as long as it isn't blocked by a required select/relation we can't
guess.

Official docs: https://developers.notion.com/reference/post-page
"""

from __future__ import annotations

import logging

import httpx

from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.integrations.notion")

_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"
_TIMEOUT = 15.0

# contact field -> candidate Notion property names (case-insensitive) we'll
# fill if a property with that name and a compatible type exists.
_FIELD_CANDIDATES = {
    "email": ["email"],
    "phone": ["phone", "phone number"],
    "title": ["title", "job title"],
    "source": ["source"],
    "lead_score": ["score", "lead score"],
}


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": _VERSION,
        "Content-Type": "application/json",
    }


def _raise_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("message", resp.text)
    except Exception:
        detail = resp.text
    logger.warning("Notion API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"Notion API error during {context}: {detail}",
        code="notion_api_error",
        status_code=502,
    )


async def get_database_schema(api_key: str, database_id: str) -> dict[str, str]:
    """Return {property_name: property_type} for the target database."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{_API}/databases/{database_id}", headers=_headers(api_key))
        _raise_error(resp, "get_database_schema")
        props = resp.json().get("properties", {})
        return {name: meta.get("type", "") for name, meta in props.items()}


def _build_properties(schema: dict[str, str], contact: dict) -> dict:
    """Map a contact dict to Notion property payloads, using only properties
    that exist in the target schema with a type we can fill."""
    by_lower = {name.lower(): (name, ptype) for name, ptype in schema.items()}
    props: dict = {}

    # Title property (required by every Notion database) — full name.
    title_name = next((name for name, ptype in schema.items() if ptype == "title"), None)
    if title_name:
        full_name = " ".join(p for p in (contact.get("first_name"), contact.get("last_name")) if p) or contact.get("email", "")
        props[title_name] = {"title": [{"text": {"content": full_name[:2000]}}]}

    def _set_text(name: str, ptype: str, value):
        if value is None or value == "":
            return
        if ptype == "email":
            props[name] = {"email": str(value)}
        elif ptype == "phone_number":
            props[name] = {"phone_number": str(value)}
        elif ptype == "number":
            try:
                props[name] = {"number": float(value)}
            except (TypeError, ValueError):
                pass
        elif ptype == "rich_text":
            props[name] = {"rich_text": [{"text": {"content": str(value)[:2000]}}]}

    for field, candidates in _FIELD_CANDIDATES.items():
        value = contact.get(field)
        for candidate in candidates:
            match = by_lower.get(candidate)
            if match:
                _set_text(match[0], match[1], value)
                break

    return props


async def create_page(api_key: str, database_id: str, schema: dict[str, str], contact: dict) -> str:
    """Create a page (row) in the database for one contact. Returns the page id."""
    properties = _build_properties(schema, contact)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_API}/pages",
            headers=_headers(api_key),
            json={"parent": {"database_id": database_id}, "properties": properties},
        )
        _raise_error(resp, "create_page")
        return resp.json()["id"]

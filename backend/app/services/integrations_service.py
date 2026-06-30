"""Low-cost integrations: status, export formats, Zapier/Make webhooks.

Everything degrades gracefully when keys are absent. Inbound webhook payloads
become CRM **contacts** (not mailable marketing leads) to stay compliant.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.ssrf import validate_outbound_url
from app.services import crm_service
from app.services.social.base import adapter_status


def integration_status() -> dict:
    """Rich snapshot for the Settings page. Analytics keys are client-public."""
    return {
        "email": bool(settings.resend_api_key),
        "email_live": settings.email_enabled,
        "ai": settings.ai_enabled,
        "stripe": bool(settings.stripe_secret_key),
        "s3": settings.storage_backend == "s3" and bool(settings.s3_bucket),
        "calendly": bool(settings.calendly_api_key),
        "notion": bool(settings.notion_api_key),
        "zapier": bool(settings.zapier_webhook_secret),
        "bitly": bool(settings.bitly_access_token),
        "google_sheets": bool(settings.google_sheets_credentials_json),
        "social": adapter_status(),
        "analytics": {
            "plausible_domain": settings.plausible_domain or None,
            "posthog_key": settings.posthog_api_key or None,
            "posthog_host": settings.posthog_host,
            "ga_measurement_id": settings.ga_measurement_id or None,
        },
    }


# --- Export formats ---------------------------------------------------------
def to_notion_markdown(headers: list[str], rows: list[list]) -> str:
    """Markdown table that pastes cleanly into Notion (also valid GitHub MD)."""
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(out)


async def export_contacts(
    db: AsyncSession, *, brand_id: uuid.UUID | None, fmt: str
) -> tuple[str, str]:
    """Return (content, media_type). fmt: csv (Airtable/Sheets) | notion (markdown)."""
    contacts = await crm_service.list_contacts(db, brand_id=brand_id, limit=200)
    if fmt == "notion":
        rows = [[c.first_name or "", c.last_name or "", c.email or "", c.title or "",
                 c.source or "", c.lead_score] for c in contacts]
        md = to_notion_markdown(
            ["First", "Last", "Email", "Title", "Source", "Score"], rows)
        return md, "text/markdown"
    return crm_service.contacts_to_csv(contacts), "text/csv"


# --- Zapier / Make inbound --------------------------------------------------
_REPLAY_TOLERANCE = 5 * 60


def verify_inbound_signature(
    payload: bytes, signature: str | None, timestamp: str | None
) -> bool:
    """HMAC over ``{timestamp}.{body}`` with replay protection (rejects stale
    timestamps), mirroring the Stripe/Svix scheme."""
    secret = settings.zapier_webhook_secret
    if not (secret and signature and timestamp):
        return False
    try:
        if abs(time.time() - int(timestamp)) > _REPLAY_TOLERANCE:
            return False
    except ValueError:
        return False
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


async def handle_inbound_contact(db: AsyncSession, data: dict) -> dict:
    """Create a CRM contact from an inbound automation payload (NOT a mailable
    lead — opt-in must happen through the consent flow)."""
    brand_id = data.get("brand_id")
    contact = await crm_service.create_contact(db, {
        "brand_id": uuid.UUID(brand_id) if brand_id else None,
        "first_name": data.get("first_name"), "last_name": data.get("last_name"),
        "email": (data.get("email") or None) and data["email"].lower(),
        "phone": data.get("phone"), "title": data.get("title"),
        "source": data.get("source") or "zapier_inbound",
    })
    return {"contact_id": str(contact.id)}


# --- Outbound dispatch (event hooks; SSRF-guarded) --------------------------
async def dispatch_outbound(url: str, payload: dict) -> bool:
    """POST an event to a Zapier/Make webhook URL. The URL must be on the SSRF
    allowlist. Returns True on a 2xx response."""
    validate_outbound_url(url)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        return resp.is_success

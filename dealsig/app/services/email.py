"""Single outbound-email integration point.

Every Resend call in the app goes through send_via_resend so the From address,
Reply-To policy, timeout, and tagging stay consistent and are configured in one
place. Callers supply content; they never build the HTTP request themselves.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailNotConfigured(RuntimeError):
    """Resend credentials are missing for a send that requires them."""


async def send_via_resend(
    *,
    to: list[str],
    subject: str,
    text: str,
    html: str = "",
    category: str = "",
    reply_to: list[str] | None = None,
    idempotency_key: str = "",
) -> None:
    settings = get_settings()
    if not settings.resend_api_key or not settings.resend_from_email:
        raise EmailNotConfigured("Resend email delivery is not configured")
    if not to:
        raise EmailNotConfigured("No recipient configured for this email")

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
        "User-Agent": "DealSigAI/0.1",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    payload: dict = {
        "from": settings.resend_from_email,
        "to": to,
        "subject": subject,
        "text": text,
    }
    if html:
        payload["html"] = html
    if category:
        payload["tags"] = [{"name": "category", "value": category}]

    # Caller-supplied addresses come first so the contact form can make Reply go
    # to the person who wrote in, with RESEND_REPLY_TO kept as a fallback.
    addresses = list(reply_to or []) + settings.reply_to_list
    deduped = list(dict.fromkeys(address for address in addresses if address))
    if deduped:
        payload["reply_to"] = deduped

    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.post(RESEND_ENDPOINT, headers=headers, json=payload)
    response.raise_for_status()

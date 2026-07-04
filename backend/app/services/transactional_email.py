"""Lightweight transactional email for auth/account flows.

Sends directly via the configured provider without the marketing compliance
pipeline (no suppression check, no consent gate) — appropriate for operational
emails to our own registered users (verification, invitations, password resets).
"""

from __future__ import annotations

from app.config import settings
from app.services.email_service import get_provider


def send_transactional(to_email: str, subject: str, html: str, text: str = "") -> None:
    """Fire a single transactional email. No-op in test mode (TestProvider logs it)."""
    payload: dict = {
        "from": f"{settings.default_from_name} <{settings.default_from_email}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    get_provider().send(payload)

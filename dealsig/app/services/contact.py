"""Contact / feedback / feature-request form delivery.

Submissions are emailed to the CONTACT_RECIPIENTS inboxes through the shared
Resend integration. Nothing is persisted: the mailbox is the record.

The form is a public, unauthenticated endpoint that causes email to be sent, so
it is deliberately narrow — it can only ever deliver to the operator-configured
recipients. A submitter never chooses who receives the message, which is what
keeps it from being usable as an open relay.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, time, timezone
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ContactMessage
from app.services.email import send_via_resend

TOPICS: dict[str, str] = {
    "feedback": "Feedback",
    "feature_request": "Feature request",
    "bug": "Something is broken",
    "data_source": "Data source suggestion",
    "billing": "Billing or account",
    "other": "Other",
}

MAX_NAME = 120
MAX_SUBJECT = 200
MAX_MESSAGE = 4000
MIN_MESSAGE = 10


class ContactNotConfigured(RuntimeError):
    """CONTACT_RECIPIENTS (or Resend) is unset, so the form cannot deliver."""


class DailyLimitReached(RuntimeError):
    """Today's contact-email budget is spent; refuse rather than spend more."""


def _hashed(value: str) -> str:
    """Store a fingerprint, not the value — this table holds no plaintext PII."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest() if value else ""


def delivered_today(db: Session) -> int:
    start_of_day = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    return db.scalar(
        select(func.count())
        .select_from(ContactMessage)
        .where(ContactMessage.created_at >= start_of_day)
    ) or 0


def daily_budget_remaining(db: Session) -> int | None:
    """Sends left today, or None when CONTACT_DAILY_LIMIT is 0 (no cap — default)."""
    limit = get_settings().contact_daily_limit
    if limit <= 0:
        return None
    return max(0, limit - delivered_today(db))


def record_delivery(db: Session, submission: "ContactSubmission", client_key: str = "") -> None:
    db.add(
        ContactMessage(
            topic=submission.topic,
            email_hash=_hashed(submission.email),
            client_hash=_hashed(client_key),
        )
    )
    db.commit()


@dataclass(frozen=True)
class ContactSubmission:
    email: str
    message: str
    topic: str = "feedback"
    name: str = ""
    subject: str = ""
    account_email: str = ""
    page_url: str = ""


def _single_line(value: str, limit: int) -> str:
    """Collapse whitespace so submitted text cannot smuggle line breaks into a header."""
    return " ".join(value.split())[:limit]


def _topic_label(topic: str) -> str:
    return TOPICS.get(topic, TOPICS["other"])


def _rows(submission: ContactSubmission) -> list[tuple[str, str]]:
    rows = [
        ("Topic", _topic_label(submission.topic)),
        ("From", submission.name or "(no name given)"),
        ("Reply to", submission.email),
    ]
    if submission.account_email and submission.account_email != submission.email:
        rows.append(("Signed in as", submission.account_email))
    if submission.page_url:
        rows.append(("Sent from", submission.page_url))
    return rows


def build_subject(submission: ContactSubmission) -> str:
    detail = _single_line(submission.subject, MAX_SUBJECT)
    return f"[DealSig {_topic_label(submission.topic).lower()}] {detail or submission.email}"[:200]


def build_text(submission: ContactSubmission) -> str:
    header = "\n".join(f"{label}: {value}" for label, value in _rows(submission))
    return f"{header}\n\n{submission.message.strip()}\n"


def build_html(submission: ContactSubmission) -> str:
    # Everything here is submitter-controlled, so escape it all — this email is
    # rendered in the operator's own mail client.
    rows = "".join(
        f"<tr><td style='padding:4px 14px 4px 0;color:#87948f'>{escape(label)}</td>"
        f"<td style='padding:4px 0;color:#10201c'>{escape(value)}</td></tr>"
        for label, value in _rows(submission)
    )
    body = escape(submission.message.strip()).replace("\n", "<br>")
    return (
        "<div style='font-family:Arial,sans-serif;max-width:640px;padding:24px'>"
        "<p style='color:#60706a;font-size:13px'>DEALSIG AI · CONTACT FORM</p>"
        f"<h1 style='color:#10201c;font-size:22px'>{escape(_topic_label(submission.topic))}</h1>"
        f"<table style='font-size:13px;border-collapse:collapse'>{rows}</table>"
        "<hr style='margin:18px 0;border:0;border-top:1px solid #e3e8e2'>"
        f"<div style='color:#2c3a35;font-size:14px;line-height:1.6'>{body}</div>"
        "</div>"
    )


async def send_contact_message(submission: ContactSubmission, db: Session | None = None) -> None:
    settings = get_settings()
    recipients = settings.contact_recipient_list
    if not recipients or not settings.resend_api_key or not settings.resend_from_email:
        raise ContactNotConfigured(
            "Set RESEND_API_KEY, RESEND_FROM_EMAIL and CONTACT_RECIPIENTS to enable the form"
        )
    # Only when the operator opted into a cap, and checked immediately before
    # the send so a burst cannot slip past a value read earlier in the request.
    if db is not None:
        remaining = daily_budget_remaining(db)
        if remaining is not None and remaining <= 0:
            raise DailyLimitReached(
                f"Contact form reached its {settings.contact_daily_limit}/day delivery cap"
            )
    fingerprint = hashlib.sha256(
        f"{submission.email}:{submission.subject}:{submission.message}".encode()
    ).hexdigest()[:40]
    await send_via_resend(
        to=recipients,
        subject=build_subject(submission),
        text=build_text(submission),
        html=build_html(submission),
        category="contact_form",
        # Reply goes to the submitter; RESEND_REPLY_TO is appended after it.
        reply_to=[submission.email],
        idempotency_key=f"contact-{fingerprint}",
    )

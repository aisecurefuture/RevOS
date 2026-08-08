"""Stateless bot challenge for the public contact form.

A bare "I am not a robot" checkbox is a form field, and a bot sets form fields.
So the checkbox is only the visible part: ticking it makes the browser solve a
proof-of-work over a server-signed nonce, and the submit button stays disabled
until it does.

What each layer actually stops:
- HMAC signature: a bot cannot mint its own challenge, so it must GET the form
  before it can POST. That alone defeats the common "POST straight at the
  endpoint" script.
- Issued-at timestamp: rejects submissions faster than a human can type and
  expires stale tokens.
- Proof of work: makes every attempt cost real CPU, so volume gets expensive.

None of this is unbreakable — a determined attacker with a headless browser gets
through. The hard guarantee against burning the Resend quota is the daily send
cap in app/services/contact.py; this layer is what keeps casual bots from ever
reaching it.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from app.config import get_settings

# Below this, a human could not have read and filled the form.
MIN_SECONDS = 3
# A form left open longer than this must be reloaded.
MAX_SECONDS = 2 * 60 * 60


class ChallengeError(ValueError):
    """The submitted challenge is missing, forged, stale, or unsolved."""


def _signature(issued_at: int, nonce: str, session_token: str) -> str:
    settings = get_settings()
    message = f"{issued_at}:{nonce}:{session_token}".encode()
    return hmac.new(settings.session_secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def issue(session_token: str, *, now: int | None = None) -> str:
    """Mint a challenge bound to this session. Format: issued_at.nonce.signature"""
    issued_at = int(time.time()) if now is None else now
    nonce = secrets.token_urlsafe(12)
    return f"{issued_at}.{nonce}.{_signature(issued_at, nonce, session_token)}"


def _leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for byte in digest:
        if byte:
            return bits + (8 - byte.bit_length())
        bits += 8
    return bits


def solution_is_valid(nonce: str, counter: str, difficulty_bits: int) -> bool:
    digest = hashlib.sha256(f"{nonce}:{counter}".encode()).digest()
    return _leading_zero_bits(digest) >= difficulty_bits


def verify(
    token: str,
    counter: str,
    session_token: str,
    *,
    difficulty_bits: int | None = None,
    now: int | None = None,
) -> None:
    """Raise ChallengeError unless this is a fresh, correctly-solved challenge."""
    settings = get_settings()
    bits = settings.contact_pow_bits if difficulty_bits is None else difficulty_bits
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise ChallengeError("Verification is missing. Reload the page and tick the box again.")
    raw_issued_at, nonce, signature = parts
    try:
        issued_at = int(raw_issued_at)
    except ValueError as exc:
        raise ChallengeError("Verification is malformed. Reload the page.") from exc

    # Constant-time compare, and note the signature covers the session token, so
    # a challenge minted for one visitor cannot be replayed by another.
    if not hmac.compare_digest(signature, _signature(issued_at, nonce, session_token)):
        raise ChallengeError("Verification failed. Reload the page and tick the box again.")

    age = (int(time.time()) if now is None else now) - issued_at
    if age < MIN_SECONDS:
        raise ChallengeError("That was submitted faster than a person could type it.")
    if age > MAX_SECONDS:
        raise ChallengeError("This form expired. Reload the page and try again.")

    if not counter or not counter.isdigit() or len(counter) > 20:
        raise ChallengeError("Verification is incomplete. Tick the box and wait for it to finish.")
    if not solution_is_valid(nonce, counter, bits):
        raise ChallengeError("Verification failed. Reload the page and tick the box again.")

"""TOTP 2FA primitives (Phase 2 M2).

- TOTP secrets are **Fernet-encrypted at rest** with a key derived from
  ``SECRET_KEY`` and stored in Postgres, so verifying a login never depends on
  OpenBao being unsealed.
- Recovery codes are shown once and stored only as SHA-256 hashes.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_ISSUER = "RevOS"


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """otpauth:// URI the client renders as a QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER)


def verify_code(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP with a ±1 step (30s) window for clock skew."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# --- Recovery codes ---------------------------------------------------------
def generate_recovery_codes(n: int = 10) -> list[str]:
    """Human-friendly one-time codes (shown once)."""
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()

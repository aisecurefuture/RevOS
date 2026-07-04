"""OpenBao / Vault KV v2 secrets service.

Provides async read/write/delete/list operations against an OpenBao (or
HashiCorp Vault) instance using KV v2.  All network I/O is done via httpx
with short timeouts; failures are wrapped as RevOSError(503).

Path convention for social OAuth tokens:
    revos/accounts/{account_id}/social/{platform}

When ``settings.bao_token`` is empty the service is considered disabled and
any write/read call immediately raises RevOSError(503, code="bao_unavailable").
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.secrets")

_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _client() -> httpx.AsyncClient:
    """Return a configured AsyncClient.

    Raises RevOSError(503) if the token is not configured (service disabled).
    A new client is created per call — simpler than managing a persistent
    connection pool in an async context.
    """
    if not settings.bao_token:
        raise RevOSError(
            "Secrets service is not configured (BAO_TOKEN missing).",
            code="bao_unavailable",
            status_code=503,
        )
    return httpx.AsyncClient(
        base_url=settings.bao_addr,
        headers={"X-Vault-Token": settings.bao_token},
        timeout=_TIMEOUT,
    )


def _data_url(path: str) -> str:
    """KV v2 data endpoint (read/write)."""
    return f"/v1/{settings.bao_kv_mount}/data/{path}"


def _metadata_url(path: str) -> str:
    """KV v2 metadata endpoint (delete-all-versions / list)."""
    return f"/v1/{settings.bao_kv_mount}/metadata/{path}"


def _raise_for_status(resp: httpx.Response, *, allow_404: bool = False) -> None:
    """Raise RevOSError for non-2xx responses (optionally ignoring 404)."""
    if resp.is_success:
        return
    if allow_404 and resp.status_code == 404:
        return
    raise RevOSError(
        f"OpenBao returned HTTP {resp.status_code}.",
        code="bao_error",
        status_code=502,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def put_secret(path: str, data: dict) -> None:
    """Write *data* to *path* in KV v2."""
    try:
        async with _client() as client:
            resp = await client.post(_data_url(path), json={"data": data})
    except httpx.HTTPError as exc:
        logger.warning("OpenBao write failed: %s", exc)
        raise RevOSError(
            "Secrets service unavailable.", code="bao_unavailable", status_code=503
        ) from exc
    _raise_for_status(resp)


async def get_secret(path: str) -> dict | None:
    """Read the latest version of *path*.

    Returns the inner ``data`` dict, or ``None`` if the path does not exist.
    """
    try:
        async with _client() as client:
            resp = await client.get(_data_url(path))
    except httpx.HTTPError as exc:
        logger.warning("OpenBao read failed: %s", exc)
        raise RevOSError(
            "Secrets service unavailable.", code="bao_unavailable", status_code=503
        ) from exc
    if resp.status_code == 404:
        return None
    _raise_for_status(resp)
    # KV v2: {"data": {"data": {...}, "metadata": {...}}}
    return resp.json()["data"]["data"]


async def delete_secret(path: str) -> None:
    """Delete all versions of the secret at *path* (metadata delete)."""
    try:
        async with _client() as client:
            resp = await client.delete(_metadata_url(path))
    except httpx.HTTPError as exc:
        logger.warning("OpenBao delete failed: %s", exc)
        raise RevOSError(
            "Secrets service unavailable.", code="bao_unavailable", status_code=503
        ) from exc
    _raise_for_status(resp)


async def list_secrets(path: str) -> list[str]:
    """List keys under *path* (non-recursive).

    Returns the ``keys`` list from the KV v2 LIST response.
    """
    try:
        async with _client() as client:
            resp = await client.request("LIST", _metadata_url(path))
    except httpx.HTTPError as exc:
        logger.warning("OpenBao list failed: %s", exc)
        raise RevOSError(
            "Secrets service unavailable.", code="bao_unavailable", status_code=503
        ) from exc
    _raise_for_status(resp)
    # KV v2: {"data": {"keys": [...]}}
    return resp.json()["data"]["keys"]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def account_social_path(account_id: object, platform: str) -> str:
    """Return the canonical KV path for a social OAuth token.

    Example:
        account_social_path("abc123", "meta")
        # → "revos/accounts/abc123/social/meta"
    """
    return f"revos/accounts/{account_id}/social/{platform}"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def is_healthy() -> bool:
    """Return True if OpenBao is reachable and unsealed.

    Calls ``/v1/sys/health`` (no authentication required).  Returns False on
    any network error, HTTP error, or if the instance is sealed.
    """
    try:
        async with httpx.AsyncClient(base_url=settings.bao_addr, timeout=_TIMEOUT) as client:
            resp = await client.get("/v1/sys/health")
        payload = resp.json()
        return payload.get("sealed") is False
    except Exception as exc:  # noqa: BLE001 — health check must never raise
        logger.debug("OpenBao health check failed: %s", exc)
        return False

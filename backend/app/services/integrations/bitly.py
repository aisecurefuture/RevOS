"""Bitly link shortening — Phase 3.

Official docs: https://dev.bitly.com/api-reference/#createBitlink
"""

from __future__ import annotations

import logging

import httpx

from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.integrations.bitly")

_API = "https://api-ssl.bitly.com/v4"
_TIMEOUT = 10.0


def _raise_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("message", resp.text)
    except Exception:
        detail = resp.text
    logger.warning("Bitly API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"Bitly API error during {context}: {detail}",
        code="bitly_api_error",
        status_code=502,
    )


async def shorten(access_token: str, long_url: str) -> str:
    """Shorten a URL. Returns the bit.ly short link."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_API}/shorten",
            json={"long_url": long_url},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _raise_error(resp, "shorten")
        return resp.json()["link"]

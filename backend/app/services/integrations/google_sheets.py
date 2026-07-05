"""Google Sheets API — push CRM contacts via a service account — Phase 3.

No google-api-python-client dependency: we hand-roll the service-account
OAuth2 JWT-bearer flow with ``pyjwt`` (RS256, already a dependency for other
signed tokens) against the customer's pasted service-account JSON key, then
call the Sheets REST API directly with httpx.

The customer must share their target spreadsheet with the service account's
``client_email`` (Editor access) — same as any other Sheets service-account
integration.

Official docs:
  https://developers.google.com/identity/protocols/oauth2/service-account
  https://developers.google.com/sheets/api/reference/rest
"""

from __future__ import annotations

import json
import logging
import time

import httpx
import jwt

from app.core.exceptions import RevOSError

logger = logging.getLogger("revos.integrations.google_sheets")

_SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_TIMEOUT = 15.0


def parse_service_account(raw_json: str) -> dict:
    """Validate the pasted JSON and return the parsed dict.

    Raises RevOSError on malformed input so the caller can surface a clear
    400 instead of a raw JSON/KeyError.
    """
    try:
        data = json.loads(raw_json)
    except (ValueError, TypeError) as exc:
        raise RevOSError(
            "That doesn't look like a valid service-account JSON key.",
            code="invalid_service_account", status_code=400,
        ) from exc
    missing = [k for k in ("client_email", "private_key", "token_uri") if not data.get(k)]
    if missing:
        raise RevOSError(
            f"Service-account JSON is missing required field(s): {', '.join(missing)}.",
            code="invalid_service_account", status_code=400,
        )
    return data


def _raise_error(resp: httpx.Response, context: str) -> None:
    if resp.is_success:
        return
    try:
        detail = resp.json().get("error", {})
        if isinstance(detail, dict):
            detail = detail.get("message", resp.text)
    except Exception:
        detail = resp.text
    logger.warning("Google Sheets API error (%s): HTTP %s — %s", context, resp.status_code, detail)
    raise RevOSError(
        f"Google Sheets API error during {context}: {detail}",
        code="google_sheets_api_error",
        status_code=502,
    )


async def get_access_token(service_account: dict) -> str:
    """Mint a short-lived OAuth2 access token via the JWT-bearer grant."""
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": service_account["client_email"],
            "scope": _SCOPE,
            "aud": service_account["token_uri"],
            "iat": now,
            "exp": now + 3600,
        },
        service_account["private_key"],
        algorithm="RS256",
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            service_account["token_uri"],
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        _raise_error(resp, "get_access_token")
        return resp.json()["access_token"]


async def append_rows(access_token: str, spreadsheet_id: str, rows: list[list]) -> int:
    """Append rows to the sheet's first tab. Returns the number of rows appended."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_SHEETS_API}/{spreadsheet_id}/values/A1:append",
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            headers={"Authorization": f"Bearer {access_token}"},
            json={"values": rows},
        )
        _raise_error(resp, "append_rows")
        return len(rows)

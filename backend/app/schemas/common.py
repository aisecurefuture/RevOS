"""Shared response/query schemas and reusable field types."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def _require_http_url(value: str | None) -> str | None:
    """Reject non-http(s) URLs (e.g. javascript:) before they are stored and
    later rendered as href/src — a stored-XSS defense."""
    if value is None or value == "":
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("URL must start with http:// or https://")
    return value


# Optional http(s) URL string usable in any schema.
HttpUrlStr = Annotated[str, AfterValidator(_require_http_url)]


class Message(BaseModel):
    status: str
    detail: str | None = None


class Pagination(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

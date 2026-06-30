"""Global request body-size ceiling (DoS guard).

Rejects oversized requests by Content-Length BEFORE the body is read into
memory. Per-route caps (e.g. media upload) still apply on top of this hard
ceiling.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"error": {"code": "payload_too_large",
                                           "message": "Request body too large."}},
                    )
            except ValueError:
                pass
        return await call_next(request)

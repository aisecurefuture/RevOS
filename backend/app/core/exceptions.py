"""Application error types and safe error handlers.

Error responses never leak internals (stack traces, SQL, secret values).
Unexpected errors return a generic envelope; details are logged server-side.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("revos")


class RevOSError(Exception):
    """Base class for domain errors with a safe, user-facing message."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(RevOSError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class PermissionError_(RevOSError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class AuthError(RevOSError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ConflictError(RevOSError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ComplianceError(RevOSError):
    """Raised when an action would violate consent/suppression/approval rules."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "compliance_blocked"


class PaymentRequiredError(RevOSError):
    """Raised when an action requires a paid plan the account does not have."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "payment_required"


def _envelope(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RevOSError)
    async def _handle_revos_error(request: Request, exc: RevOSError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder makes details JSON-safe (Pydantic `ctx` may hold a
        # raw exception object). Errors are safe to surface — no internals.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "validation_error", "message": "Invalid request.",
                               "details": jsonable_encoder(exc.errors())}},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log full detail server-side; return an opaque message to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred."),
        )

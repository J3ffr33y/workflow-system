"""Typed application errors. The API layer maps them to HTTP responses.

Every error carries a stable machine `code` (the frontend switches on it and
translates it) plus an English developer message and optional details.
"""

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class Conflict(AppError):
    """The record changed since the caller read it, or a uniqueness rule failed."""

    status_code = 409
    code = "conflict"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"

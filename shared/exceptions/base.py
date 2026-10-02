"""Domain exceptions for all discussion forum services."""

from __future__ import annotations

from typing import Any


class DomainException(Exception):
    """Base class for all business and domain-level exceptions."""

    default_message: str = "A domain error occurred."
    default_code: str = "DOMAIN_ERROR"
    status_code: int = 400

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or {}


class EntityNotFoundException(DomainException):
    """Raised when a requested resource does not exist."""

    default_message = "The requested resource was not found."
    default_code = "NOT_FOUND"
    status_code = 404


class AuthenticationFailedException(DomainException):
    """Raised when authentication credentials are missing or invalid."""

    default_message = "Authentication failed or token is invalid."
    default_code = "AUTHENTICATION_FAILED"
    status_code = 401


class PermissionDeniedException(DomainException):
    """Raised when user lacks permission to perform the requested action."""

    default_message = "You do not have permission to perform this action."
    default_code = "PERMISSION_DENIED"
    status_code = 403


class ValidationException(DomainException):
    """Raised when business validation rules fail."""

    default_message = "The provided data failed validation."
    default_code = "VALIDATION_ERROR"
    status_code = 422


class ConflictException(DomainException):
    """Raised when an entity conflicts with existing state (e.g., unique violation)."""

    default_message = "Resource state conflict or already exists."
    default_code = "RESOURCE_CONFLICT"
    status_code = 409


class RateLimitExceededException(DomainException):
    """Raised when an operation exceeds allowed rate or frequency."""

    default_message = "Rate limit exceeded. Please slow down."
    default_code = "RATE_LIMIT_EXCEEDED"
    status_code = 429

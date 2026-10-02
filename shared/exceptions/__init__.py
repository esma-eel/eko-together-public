"""Shared domain exceptions and error handling."""

from shared.exceptions.base import (
    AuthenticationFailedException,
    ConflictException,
    DomainException,
    EntityNotFoundException,
    PermissionDeniedException,
    RateLimitExceededException,
    ValidationException,
)
from shared.exceptions.handlers import (
    APIErrorDetail,
    domain_exception_to_dmr_error,
    format_domain_error_payload,
)

__all__ = [
    "APIErrorDetail",
    "AuthenticationFailedException",
    "ConflictException",
    "DomainException",
    "EntityNotFoundException",
    "PermissionDeniedException",
    "RateLimitExceededException",
    "ValidationException",
    "domain_exception_to_dmr_error",
    "format_domain_error_payload",
]

"""Unit tests for domain exceptions and DMR error formatting."""

from __future__ import annotations

from http import HTTPStatus

from dmr import APIError

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
    domain_exception_to_dmr_error,
    format_domain_error_payload,
)


def test_domain_exception_defaults() -> None:
    exc = DomainException("Something failed")
    assert exc.message == "Something failed"
    assert exc.status_code == 400
    assert exc.code == "DOMAIN_ERROR"


def test_specific_domain_exceptions() -> None:
    not_found = EntityNotFoundException("Post not found")
    assert not_found.status_code == 404
    assert not_found.code == "NOT_FOUND"

    perm = PermissionDeniedException()
    assert perm.status_code == 403
    assert perm.code == "PERMISSION_DENIED"

    auth = AuthenticationFailedException("Token expired")
    assert auth.status_code == 401
    assert auth.code == "AUTHENTICATION_FAILED"

    val = ValidationException("Invalid email format", details={"field": "email"})
    assert val.status_code == 422
    assert val.details == {"field": "email"}

    conflict = ConflictException("Username already in use")
    assert conflict.status_code == 409

    rate = RateLimitExceededException()
    assert rate.status_code == 429


def test_format_domain_error_payload() -> None:
    exc = EntityNotFoundException("User not found", details={"user_id": "123"})
    payload = format_domain_error_payload(exc)

    assert payload.code == "NOT_FOUND"
    assert payload.message == "User not found"
    assert payload.status_code == 404
    assert payload.details == {"user_id": "123"}
    assert payload.timestamp is not None


def test_domain_exception_to_dmr_error() -> None:
    exc = PermissionDeniedException("Moderator role required")
    dmr_err = domain_exception_to_dmr_error(exc)

    assert isinstance(dmr_err, APIError)
    assert dmr_err.status_code == HTTPStatus.FORBIDDEN
    assert dmr_err.raw_data.code == "PERMISSION_DENIED"
    assert dmr_err.raw_data.status_code == 403

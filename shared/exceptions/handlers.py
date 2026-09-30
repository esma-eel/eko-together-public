"""Standardized RFC 7807 problem details and DMR error handler integration."""

from __future__ import annotations

import datetime
from http import HTTPStatus
from typing import Any

import msgspec
from dmr import APIError

from shared.exceptions.base import (
    DomainException,
)


class APIErrorDetail(msgspec.Struct, kw_only=True):
    """Standardized API Error response body."""

    code: str
    message: str
    status_code: int
    details: dict[str, Any] = msgspec.field(default_factory=dict)
    timestamp: str = msgspec.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )


def format_domain_error_payload(exc: DomainException) -> APIErrorDetail:
    """Format a DomainException into a standardized APIErrorDetail."""
    return APIErrorDetail(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


def domain_exception_to_dmr_error(exc: DomainException) -> APIError:
    """Convert a shared DomainException into a typed django-modern-rest APIError."""
    payload = format_domain_error_payload(exc)
    status = HTTPStatus(exc.status_code)
    # Return typed APIError recognized by DMR pipeline
    return APIError(
        payload,
        status_code=status,
    )

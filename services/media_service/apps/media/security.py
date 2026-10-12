"""Decentralized RS256 JWT Authentication and User Throttling for Media Service.

Validates asymmetric RS256 JWT tokens using the RSA Public Key.
Does NOT perform any database queries to the Auth Service (pure stateless microservice architecture).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Literal, Self

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from dmr.openapi.objects import Reference, SecurityRequirement, SecurityScheme
from dmr.security import AuthenticatedHttpRequest, SyncAuth
from dmr.throttling.cache_keys import BaseThrottleCacheKey
from typing_extensions import override

from shared.exceptions.base import AuthenticationFailedException
from shared.exceptions.handlers import domain_exception_to_dmr_error
from shared.jwt.tokens import AuthenticatedClaims, load_public_key, verify_and_decode_token

if TYPE_CHECKING:
    from dmr import Controller
    from dmr.endpoint import Endpoint
    from dmr.serializer import BaseSerializer


class AuthenticatedMediaHttpRequest(AuthenticatedHttpRequest[AnonymousUser]):
    """Typed request for authenticated media endpoints containing JWT claims."""

    claims: AuthenticatedClaims


class RS256JWTSyncAuth(SyncAuth):
    """Enforces a valid RS256 JWT Bearer token on media endpoints."""

    __slots__ = ("public_key_pem", "security_scheme_name")

    def __init__(
        self,
        *,
        security_scheme_name: str = "BearerAuth",
    ) -> None:
        self.security_scheme_name = security_scheme_name
        self.public_key_pem = load_public_key(settings.JWT_PUBLIC_KEY_PATH)

    @property
    def www_authenticate_challenge(self) -> str | None:
        """Challenge naming the scheme this auth expects."""
        return "Bearer"

    @property
    def security_schemes(self) -> dict[str, SecurityScheme | Reference]:
        """Describe Bearer token mechanism for OpenAPI."""
        return {
            self.security_scheme_name: SecurityScheme(
                type="http",
                scheme="bearer",
                bearer_format="JWT",
                description="RS256 Asymmetric JWT Bearer token authentication.",
            ),
        }

    @property
    def security_requirement(self) -> SecurityRequirement:
        return {self.security_scheme_name: []}

    def __call__(
        self,
        endpoint: Endpoint,
        controller: Controller[BaseSerializer],
    ) -> Self | None:
        """Validate Bearer token from Authorization header."""
        auth_header = controller.request.headers.get(
            "Authorization"
        ) or controller.request.META.get("HTTP_AUTHORIZATION")
        if not auth_header:
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException(
                    "Invalid Authorization header format. Expected 'Bearer <token>'."
                )
            )

        token = parts[1]

        try:
            claims = verify_and_decode_token(
                token=token,
                public_key_pem=self.public_key_pem,
                expected_token_type="access",
            )
        except AuthenticationFailedException as exc:
            raise domain_exception_to_dmr_error(exc) from exc
        except Exception as exc:
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException(f"Token verification failed: {exc}")
            ) from exc

        # Attach claims and anonymous user to request
        controller.request.user = AnonymousUser()
        controller.request.claims = claims
        return self


@dataclasses.dataclass(slots=True, frozen=True, kw_only=True)
class UserClaimsProfileThrottleKey(BaseThrottleCacheKey):
    """Rate-limiting cache key scoped to authenticated user profile ID (30 req/min)."""

    runs_before_auth: Literal[False] = False
    name: str = "UserClaimsProfileThrottleKey"

    @override
    def __call__(
        self,
        endpoint: Endpoint,
        controller: Controller[BaseSerializer],
    ) -> str | None:
        """Return cache key based on user profile ID or IP address fallback."""
        claims = getattr(controller.request, "claims", None)
        if claims and getattr(claims, "profile_id", None):
            return f"media_upload_user_{claims.profile_id}"
        # Fallback to remote IP if claims not populated
        return f"media_upload_ip_{controller.request.META.get('REMOTE_ADDR', 'unknown')}"

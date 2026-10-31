"""Decentralized RS256 JWT Authentication for Feed Service.

Validates asymmetric RS256 JWT tokens using the RSA Public Key.
Does NOT perform any synchronous database queries to Auth Service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from dmr.openapi.objects import Reference, SecurityRequirement, SecurityScheme
from dmr.security import AuthenticatedHttpRequest, SyncAuth

from shared.exceptions.base import AuthenticationFailedException
from shared.exceptions.handlers import domain_exception_to_dmr_error
from shared.jwt.tokens import AuthenticatedClaims, load_public_key, verify_and_decode_token

if TYPE_CHECKING:
    from dmr import Controller
    from dmr.endpoint import Endpoint
    from dmr.serializer import BaseSerializer


class AuthenticatedFeedHttpRequest(AuthenticatedHttpRequest[AnonymousUser]):
    """Typed request for authenticated feed endpoints containing JWT claims."""

    claims: AuthenticatedClaims


class RS256JWTSyncAuth(SyncAuth):
    """Enforces a valid RS256 JWT Bearer token on feed endpoints."""

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
        return "Bearer"

    @property
    def security_schemes(self) -> dict[str, SecurityScheme | Reference]:
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
        auth_header = controller.request.headers.get(
            "Authorization"
        ) or controller.request.META.get("HTTP_AUTHORIZATION")
        if not auth_header:
            return None

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

        controller.request.user = AnonymousUser()
        controller.request.claims = claims
        return self


class OptionalRS256JWTSyncAuth(SyncAuth):
    """Optionally parses RS256 JWT Bearer token on feed endpoints if present."""

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
        return "Bearer"

    @property
    def security_schemes(self) -> dict[str, SecurityScheme | Reference]:
        return {
            self.security_scheme_name: SecurityScheme(
                type="http",
                scheme="bearer",
                bearer_format="JWT",
                description="Optional RS256 Asymmetric JWT Bearer token.",
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
        auth_header = controller.request.headers.get(
            "Authorization"
        ) or controller.request.META.get("HTTP_AUTHORIZATION")
        if not auth_header:
            return None

        parts = auth_header.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            try:
                controller.request.claims = verify_and_decode_token(
                    token=parts[1],
                    public_key_pem=self.public_key_pem,
                    expected_token_type="access",
                )
            except Exception:
                pass
        return self

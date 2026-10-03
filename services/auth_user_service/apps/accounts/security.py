"""Decentralized RS256 JWT Authentication for django-modern-rest (DMR).

Validates asymmetric RS256 JWT tokens using RSA Public Key without shared DB locks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from dmr.openapi.objects import Reference, SecurityRequirement, SecurityScheme
from dmr.security import AuthenticatedHttpRequest, SyncAuth

from services.auth_user_service.apps.accounts.models import User, UserProfile
from services.auth_user_service.apps.accounts.services import is_token_revoked
from shared.exceptions.base import AuthenticationFailedException
from shared.exceptions.handlers import domain_exception_to_dmr_error
from shared.jwt.tokens import AuthenticatedClaims, load_public_key, verify_and_decode_token

if TYPE_CHECKING:
    from dmr import Controller
    from dmr.endpoint import Endpoint
    from dmr.serializer import BaseSerializer


class AuthenticatedUserHttpRequest(AuthenticatedHttpRequest[User]):
    """Typed request for authenticated accounts endpoints."""

    user: User
    profile: UserProfile
    claims: AuthenticatedClaims


class RS256JWTSyncAuth(SyncAuth):
    """Enforces valid RS256 JWT Bearer token on DMR endpoints."""

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
            return None

        parts = auth_header.strip().split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException(
                    "Invalid Authorization header format. Expected 'Bearer <token>'."
                )
            )

        token = parts[1]

        # Check blacklist
        if is_token_revoked(token):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Token has been revoked.")
            )

        try:
            claims = verify_and_decode_token(
                token=token,
                public_key_pem=self.public_key_pem,
                issuer=settings.JWT_ISSUER,
                audience=settings.JWT_AUDIENCE,
                expected_token_type="access",
            )
        except AuthenticationFailedException as exc:
            raise domain_exception_to_dmr_error(exc) from exc
        except Exception as exc:
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException(f"Token verification failed: {exc}")
            ) from exc

        # Retrieve user and profile
        user = (
            User.objects.filter(id=claims.user_id, is_active=True).select_related("profile").first()
        )
        if not user:
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("User not found or inactive.")
            )

        # Attach to request for controller handlers
        controller.request.user = user
        controller.request.claims = claims
        controller.request.profile = user.profile
        return self


class OptionalRS256JWTSyncAuth(SyncAuth):
    """Allows anonymous requests while attaching authenticated claims if present."""

    __slots__ = ("public_key_pem", "security_scheme_name")

    def __init__(
        self,
        *,
        security_scheme_name: str = "OptionalBearerAuth",
    ) -> None:
        self.security_scheme_name = security_scheme_name
        self.public_key_pem = load_public_key(settings.JWT_PUBLIC_KEY_PATH)

    @property
    def www_authenticate_challenge(self) -> str | None:
        return None

    @property
    def security_schemes(self) -> dict[str, SecurityScheme | Reference]:
        return {
            self.security_scheme_name: SecurityScheme(
                type="http",
                scheme="bearer",
                bearer_format="JWT",
                description="Optional RS256 JWT Bearer token authentication.",
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
            controller.request.user = AnonymousUser()
            controller.request.profile = None
            controller.request.claims = None
            return self

        parts = auth_header.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            if not is_token_revoked(token):
                try:
                    claims = verify_and_decode_token(
                        token=token,
                        public_key_pem=self.public_key_pem,
                        issuer=settings.JWT_ISSUER,
                        audience=settings.JWT_AUDIENCE,
                        expected_token_type="access",
                    )
                    user = (
                        User.objects.filter(id=claims.user_id, is_active=True)
                        .select_related("profile")
                        .first()
                    )
                    if user:
                        controller.request.user = user
                        controller.request.profile = user.profile
                        controller.request.claims = claims
                        return self
                except Exception:
                    pass

        controller.request.user = AnonymousUser()
        controller.request.profile = None
        controller.request.claims = None
        return self

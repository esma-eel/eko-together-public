"""Decentralized Asymmetric JWT (RS256) utilities.

Implements token generation with RSA private key (Auth Service) and
stateless token verification with RSA public key (API Gateway & downstream services).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from shared.exceptions.base import AuthenticationFailedException, PermissionDeniedException


@dataclass(frozen=True)
class AuthenticatedClaims:
    """Parsed claims representing an authenticated user identity."""

    user_id: UUID
    profile_id: UUID
    username: str
    roles: list[str] = field(default_factory=lambda: ["user"])
    token_type: str = "access"

    def is_admin(self) -> bool:
        """Check if claims include administrative role."""
        return "admin" in self.roles or "superuser" in self.roles

    def require_admin(self) -> None:
        """Raise PermissionDeniedException if user is not an administrator."""
        if not self.is_admin():
            raise PermissionDeniedException("Administrator privileges required for this action.")


def generate_rsa_key_pair(
    private_key_path: Path | str,
    public_key_path: Path | str,
    key_size: int = 2048,
) -> tuple[bytes, bytes]:
    """Generate and save an RSA 2048-bit key pair in PEM format.

    Args:
        private_key_path: File path to save the private key PEM.
        public_key_path: File path to save the public key PEM.
        key_size: RSA bit length (default 2048).

    Returns:
        Tuple of (private_pem_bytes, public_pem_bytes).
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend(),
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path = Path(private_key_path)
    pub_path = Path(public_key_path)

    priv_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.parent.mkdir(parents=True, exist_ok=True)

    priv_path.write_bytes(private_pem)
    pub_path.write_bytes(public_pem)

    return private_pem, public_pem


def load_private_key(path_or_pem: Path | str | bytes) -> bytes:
    """Load RSA private key PEM bytes from path or raw string/bytes."""
    if isinstance(path_or_pem, Path) or (isinstance(path_or_pem, str) and "\n" not in path_or_pem):
        path = Path(path_or_pem)
        if not path.exists():
            raise FileNotFoundError(f"RSA Private key not found at: {path}")
        return path.read_bytes()
    if isinstance(path_or_pem, str):
        return path_or_pem.encode("utf-8")
    return path_or_pem


def load_public_key(path_or_pem: Path | str | bytes) -> bytes:
    """Load RSA public key PEM bytes from path or raw string/bytes."""
    if isinstance(path_or_pem, Path) or (isinstance(path_or_pem, str) and "\n" not in path_or_pem):
        path = Path(path_or_pem)
        if not path.exists():
            raise FileNotFoundError(f"RSA Public key not found at: {path}")
        return path.read_bytes()
    if isinstance(path_or_pem, str):
        return path_or_pem.encode("utf-8")
    return path_or_pem


def create_access_token(
    user_id: UUID,
    profile_id: UUID,
    username: str,
    roles: list[str],
    private_key_pem: bytes,
    expiration_minutes: int = 60,
    issuer: str = "eko-together-auth-service",
    audience: str = "eko-together-api",
) -> str:
    """Sign an asymmetric RS256 JWT access token.

    Args:
        user_id: User account UUID.
        profile_id: User profile UUID.
        username: Unique handle.
        roles: List of authorization roles (e.g. ['user', 'admin']).
        private_key_pem: RSA Private Key in PEM format.
        expiration_minutes: Token validity duration in minutes.
        issuer: JWT issuer claim.
        audience: JWT audience claim.

    Returns:
        Encoded RS256 JWT token string.
    """
    now = datetime.datetime.now(datetime.UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "profile_id": str(profile_id),
        "username": username,
        "roles": roles,
        "token_type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(minutes=expiration_minutes),
        "iss": issuer,
        "aud": audience,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def create_refresh_token(
    user_id: UUID,
    profile_id: UUID,
    username: str,
    private_key_pem: bytes,
    expiration_days: int = 7,
    issuer: str = "eko-together-auth-service",
    audience: str = "eko-together-api",
) -> str:
    """Sign an asymmetric RS256 JWT refresh token."""
    now = datetime.datetime.now(datetime.UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "profile_id": str(profile_id),
        "username": username,
        "token_type": "refresh",
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(days=expiration_days),
        "iss": issuer,
        "aud": audience,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def verify_and_decode_token(
    token: str,
    public_key_pem: bytes,
    issuer: str = "eko-together-auth-service",
    audience: str = "eko-together-api",
    expected_token_type: str = "access",
) -> AuthenticatedClaims:
    """Statelessly verify and decode an RS256 token using only the Public Key.

    Args:
        token: Raw JWT string.
        public_key_pem: RSA Public Key in PEM format.
        issuer: Expected JWT issuer claim.
        audience: Expected JWT audience claim.
        expected_token_type: 'access' or 'refresh'.

    Returns:
        Parsed AuthenticatedClaims object.

    Raises:
        AuthenticationFailedException: If signature is invalid, token expired, or claims malformed.
    """
    try:
        payload = jwt.decode(
            token,
            public_key_pem,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience,
        )
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationFailedException(
            "Token has expired. Please refresh or re-authenticate."
        ) from e
    except jwt.InvalidTokenError as e:
        raise AuthenticationFailedException(f"Invalid authentication token: {e}") from e

    token_type = payload.get("token_type")
    if token_type != expected_token_type:
        raise AuthenticationFailedException(
            f"Invalid token type: expected '{expected_token_type}', received '{token_type}'."
        )

    try:
        user_id = UUID(payload["sub"])
        profile_id = UUID(payload["profile_id"])
        username = str(payload["username"])
        roles = list(payload.get("roles", ["user"]))
    except (KeyError, ValueError, TypeError) as e:
        raise AuthenticationFailedException(f"Token claims are incomplete or corrupted: {e}") from e

    return AuthenticatedClaims(
        user_id=user_id,
        profile_id=profile_id,
        username=username,
        roles=roles,
        token_type=token_type,
    )


def extract_claims_from_headers(headers: dict[str, str]) -> AuthenticatedClaims | None:
    """Extract authenticated identity from gateway headers (X-User-Id, X-Profile-Id, X-User-Roles).

    Downstream services behind an API Gateway can use this for fast zero-cost auth.
    """
    user_id_str = headers.get("x-user-id") or headers.get("X-User-Id")
    profile_id_str = headers.get("x-profile-id") or headers.get("X-Profile-Id")
    username = headers.get("x-username") or headers.get("X-Username", "")
    roles_str = headers.get("x-user-roles") or headers.get("X-User-Roles", "user")

    if not user_id_str or not profile_id_str:
        return None

    try:
        user_id = UUID(user_id_str)
        profile_id = UUID(profile_id_str)
        roles = [r.strip() for r in roles_str.split(",") if r.strip()]
        return AuthenticatedClaims(
            user_id=user_id,
            profile_id=profile_id,
            username=username,
            roles=roles,
            token_type="access",
        )
    except (ValueError, TypeError):
        return None

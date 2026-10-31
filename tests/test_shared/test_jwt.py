"""Unit tests for asymmetric RS256 JWT tokens."""

from __future__ import annotations

from uuid import uuid4

import pytest

from shared.exceptions.base import AuthenticationFailedException, PermissionDeniedException
from shared.jwt.tokens import (
    create_access_token,
    create_refresh_token,
    extract_claims_from_headers,
    generate_rsa_key_pair,
    verify_and_decode_token,
)


@pytest.fixture(scope="module")
def rsa_keys(tmp_path_factory: pytest.TempPathFactory) -> tuple[bytes, bytes]:
    tmp_dir = tmp_path_factory.mktemp("rsa_test")
    priv_path = tmp_dir / "private.pem"
    pub_path = tmp_dir / "public.pem"
    return generate_rsa_key_pair(priv_path, pub_path, key_size=2048)


def test_jwt_access_token_creation_and_stateless_verification(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    priv_key, pub_key = rsa_keys
    user_id = uuid4()
    profile_id = uuid4()
    username = "alice"
    roles = ["user", "moderator"]

    token = create_access_token(
        user_id=user_id,
        profile_id=profile_id,
        username=username,
        roles=roles,
        private_key_pem=priv_key,
        expiration_minutes=15,
    )

    assert isinstance(token, str)
    assert len(token) > 50

    # Verification uses ONLY the public key
    claims = verify_and_decode_token(
        token=token,
        public_key_pem=pub_key,
    )

    assert claims.user_id == user_id
    assert claims.profile_id == profile_id
    assert claims.username == username
    assert claims.roles == roles
    assert claims.token_type == "access"
    assert not claims.is_admin()


def test_jwt_admin_claims(rsa_keys: tuple[bytes, bytes]) -> None:
    priv_key, pub_key = rsa_keys
    user_id = uuid4()
    profile_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        profile_id=profile_id,
        username="admin_user",
        roles=["user", "admin"],
        private_key_pem=priv_key,
    )

    claims = verify_and_decode_token(token, pub_key)
    assert claims.is_admin()
    # Should not raise
    claims.require_admin()


def test_jwt_non_admin_require_admin_raises(rsa_keys: tuple[bytes, bytes]) -> None:
    priv_key, pub_key = rsa_keys
    token = create_access_token(
        user_id=uuid4(),
        profile_id=uuid4(),
        username="regular_user",
        roles=["user"],
        private_key_pem=priv_key,
    )

    claims = verify_and_decode_token(token, pub_key)
    assert not claims.is_admin()
    with pytest.raises(PermissionDeniedException):
        claims.require_admin()


def test_jwt_expired_token(rsa_keys: tuple[bytes, bytes]) -> None:
    priv_key, pub_key = rsa_keys
    # Create token expired in the past
    token = create_access_token(
        user_id=uuid4(),
        profile_id=uuid4(),
        username="expired_user",
        roles=["user"],
        private_key_pem=priv_key,
        expiration_minutes=-5,
    )

    with pytest.raises(AuthenticationFailedException) as exc_info:
        verify_and_decode_token(token, pub_key)
    assert "expired" in str(exc_info.value).lower()


def test_jwt_tampered_token_fails(rsa_keys: tuple[bytes, bytes]) -> None:
    priv_key, pub_key = rsa_keys
    token = create_access_token(
        user_id=uuid4(),
        profile_id=uuid4(),
        username="tampered_user",
        roles=["user"],
        private_key_pem=priv_key,
    )

    # Tamper with the payload part
    parts = token.split(".")
    tampered = parts[0] + ".eyJzdWIiOiAibWFsaWNpb3VzIn0." + parts[2]

    with pytest.raises(AuthenticationFailedException):
        verify_and_decode_token(tampered, pub_key)


def test_jwt_refresh_token_type(rsa_keys: tuple[bytes, bytes]) -> None:
    priv_key, pub_key = rsa_keys
    user_id = uuid4()
    profile_id = uuid4()

    refresh_token = create_refresh_token(
        user_id=user_id,
        profile_id=profile_id,
        username="alice",
        private_key_pem=priv_key,
    )

    # Verifying as 'access' should fail
    with pytest.raises(AuthenticationFailedException) as exc_info:
        verify_and_decode_token(refresh_token, pub_key, expected_token_type="access")
    assert "expected 'access'" in str(exc_info.value)

    # Verifying as 'refresh' should succeed
    claims = verify_and_decode_token(refresh_token, pub_key, expected_token_type="refresh")
    assert claims.token_type == "refresh"


def test_extract_claims_from_gateway_headers() -> None:
    user_id = uuid4()
    profile_id = uuid4()

    headers = {
        "x-user-id": str(user_id),
        "x-profile-id": str(profile_id),
        "x-username": "gateway_user",
        "x-user-roles": "user, admin",
    }

    claims = extract_claims_from_headers(headers)
    assert claims is not None
    assert claims.user_id == user_id
    assert claims.profile_id == profile_id
    assert claims.username == "gateway_user"
    assert claims.roles == ["user", "admin"]
    assert claims.is_admin()


def test_extract_claims_missing_headers() -> None:
    claims = extract_claims_from_headers({})
    assert claims is None

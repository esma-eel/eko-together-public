"""Shared fixtures for Media Service test suite."""

import uuid
from pathlib import Path
from uuid import UUID

import pytest
from django.conf import settings
from dmr.test import DMRClient, DMRRequestFactory

from shared.jwt.tokens import create_access_token, load_private_key


@pytest.fixture
def client() -> DMRClient:
    """Fixture providing DMR test client with JSON content negotiation."""
    return DMRClient()


@pytest.fixture
def rf() -> DMRRequestFactory:
    """Fixture providing DMR request factory."""
    return DMRRequestFactory()


@pytest.fixture
def private_key_pem() -> bytes:
    """Load RSA private key for minting signed test JWTs."""
    key_path = getattr(settings, "JWT_PRIVATE_KEY_PATH", None)
    if not key_path:
        root_dir = Path(__file__).resolve().parent.parent.parent
        key_path = root_dir / "shared" / "jwt" / "private_key.pem"
    return load_private_key(key_path)


@pytest.fixture
def user_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def user_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def alt_user_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def alt_user_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_headers(
    private_key_pem: bytes,
    user_id: UUID,
    user_profile_id: UUID,
) -> dict[str, str]:
    """Provide Bearer authentication headers for primary test user."""
    token = create_access_token(
        user_id=user_id,
        profile_id=user_profile_id,
        username="media_test_user",
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def alt_auth_headers(
    private_key_pem: bytes,
    alt_user_id: UUID,
    alt_user_profile_id: UUID,
) -> dict[str, str]:
    """Provide Bearer authentication headers for alternative test user."""
    token = create_access_token(
        user_id=alt_user_id,
        profile_id=alt_user_profile_id,
        username="alt_media_user",
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def valid_upload_payload() -> dict[str, object]:
    """Standard valid payload for media presigned URL generation."""
    return {
        "filename": "system-architecture-v2.png",
        "content_type": "image/png",
        "file_size_bytes": 1048576,
        "purpose": "POST_ATTACHMENT",
    }

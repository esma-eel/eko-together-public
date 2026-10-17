"""Shared fixtures and setup for Post & Comment Service test suite."""

import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from django.conf import settings
from dmr.test import DMRClient

from services.post_comment_service.db import (
    get_comments_collection,
    get_posts_collection,
    reset_db_client,
)
from shared.jwt.tokens import create_access_token, load_private_key


@pytest.fixture
def client() -> DMRClient:
    """Provide DMR test client."""
    return DMRClient()


@pytest.fixture
def private_key_pem() -> bytes:
    """Load RSA private key for minting valid JWTs."""
    key_path = getattr(settings, "JWT_PRIVATE_KEY_PATH", None)
    if not key_path:
        root_dir = Path(__file__).resolve().parent.parent.parent
        key_path = root_dir / "shared" / "jwt" / "private_key.pem"
    return load_private_key(key_path)


@pytest.fixture
def author_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def author_user_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def other_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def author_headers(
    private_key_pem: bytes,
    author_user_id: UUID,
    author_profile_id: UUID,
) -> dict[str, str]:
    token = create_access_token(
        user_id=author_user_id,
        profile_id=author_profile_id,
        username="testauthor",
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def other_headers(
    private_key_pem: bytes,
    other_profile_id: UUID,
) -> dict[str, str]:
    token = create_access_token(
        user_id=uuid.uuid4(),
        profile_id=other_profile_id,
        username="otheruser",
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_mongo() -> Generator[None, None, None]:
    """Clean MongoDB collections before and after each test."""
    try:
        get_posts_collection().delete_many({})
        get_comments_collection().delete_many({})
    except Exception:
        pass
    yield
    try:
        get_posts_collection().delete_many({})
        get_comments_collection().delete_many({})
    except Exception:
        pass
    reset_db_client()


@pytest.fixture
def mock_events() -> Generator[list[MagicMock], None, None]:
    """Capture all emitted events across posts and comments services."""
    published = []

    def fake_publish(event):
        published.append(event)

    with (
        patch(
            "services.post_comment_service.apps.posts.services._publish_event",
            side_effect=fake_publish,
        ),
        patch(
            "services.post_comment_service.apps.comments.services._publish_event",
            side_effect=fake_publish,
        ),
    ):
        yield published

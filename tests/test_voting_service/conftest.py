"""Shared fixtures and setup for Voting Service test suite."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from django.conf import settings
from dmr.test import DMRClient

from services.post_comment_service.db import (
    get_comments_collection,
    get_posts_collection,
    reset_db_client,
)
from services.voting_service.apps.votes.models import Vote
from shared.events.base import BaseEvent
from shared.jwt.tokens import create_access_token, load_private_key


@pytest.fixture
def client() -> DMRClient:
    """Provide DMR test client."""
    return DMRClient()


@pytest.fixture
def private_key_pem() -> bytes:
    """Load RSA private key for minting valid JWTs."""
    key_path = getattr(settings, "JWT_PRIVATE_KEY_PATH", None)
    if not key_path or not Path(key_path).exists():
        root_dir = Path(__file__).resolve().parent.parent.parent
        key_path = root_dir / "keys" / "private_key.pem"
        if not key_path.exists():
            key_path = root_dir / "shared" / "jwt" / "private_key.pem"
    return load_private_key(key_path)


@pytest.fixture
def voter_user_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def voter_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def voter_headers(
    private_key_pem: bytes,
    voter_user_id: UUID,
    voter_profile_id: UUID,
) -> dict[str, str]:
    token = create_access_token(
        user_id=voter_user_id,
        profile_id=voter_profile_id,
        username="testvoter",
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def other_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def other_headers(
    private_key_pem: bytes,
    other_profile_id: UUID,
) -> dict[str, str]:
    token = create_access_token(
        user_id=uuid.uuid4(),
        profile_id=other_profile_id,
        username="othervoter",
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clean_db() -> Generator[None, None, None]:
    """Clean MongoDB documents and SQLite/Postgres votes before and after each test."""
    try:
        get_posts_collection().delete_many({})
        get_comments_collection().delete_many({})
    except Exception:
        pass
    Vote.objects.all().delete()
    yield
    try:
        get_posts_collection().delete_many({})
        get_comments_collection().delete_many({})
    except Exception:
        pass
    Vote.objects.all().delete()
    reset_db_client()


@pytest.fixture
def sample_post_id(voter_profile_id: UUID) -> UUID:
    """Insert a valid test post document in MongoDB."""
    post_id = uuid.uuid4()
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    doc = {
        "_id": str(post_id),
        "author_profile_id": str(voter_profile_id),
        "forum_id": None,
        "title": "Sample Voting Post",
        "body": "Content of voting post.",
        "image": None,
        "tags": [],
        "visibility": "PUBLIC",
        "comment_permission": "ANYONE",
        "admin_visibility": "ALL",
        "is_pinned": False,
        "pin_order": 0,
        "is_archived": False,
        "is_deleted": False,
        "upvotes_count": 0,
        "downvotes_count": 0,
        "popularity_score": 0,
        "comments_count": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    get_posts_collection().insert_one(doc)
    return post_id


@pytest.fixture
def sample_comment_id(sample_post_id: UUID, voter_profile_id: UUID) -> UUID:
    """Insert a valid test comment document in MongoDB."""
    comment_id = uuid.uuid4()
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    doc = {
        "_id": str(comment_id),
        "post_id": str(sample_post_id),
        "parent_id": None,
        "depth": 0,
        "author": {
            "id": str(voter_profile_id),
            "display_name": "Test Author",
            "avatar": None,
        },
        "body": "Sample voting comment.",
        "upvotes_count": 0,
        "downvotes_count": 0,
        "popularity_score": 0,
        "user_vote": None,
        "is_archived": False,
        "is_deleted": False,
        "reply_count": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    get_comments_collection().insert_one(doc)
    return comment_id


@pytest.fixture
def captured_events() -> Generator[list[tuple[BaseEvent, str | None]], None, None]:
    """Capture all emitted domain events and their routing keys."""
    events: list[tuple[BaseEvent, str | None]] = []

    def mock_publish(event: BaseEvent, routing_key: str | None = None, **kwargs):
        events.append((event, routing_key))
        return True

    with patch("services.voting_service.apps.votes.services.publish_domain_event", side_effect=mock_publish):
        yield events

"""Tests for Global Explore / Popular Feed API endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from dmr.test import DMRClient

from services.feed_service.apps.feed.services import REDIS_KEY_POPULAR_24H_GLOBAL
from services.voting_service.apps.votes.models import TargetType, Vote, VoteValue


@pytest.fixture
def sample_feed_posts(mock_mongo, mock_redis):
    """Seed test database with posts and populate Redis 24h rankings."""
    now = datetime.now(tz=UTC)
    p1 = str(uuid.uuid4())
    p2 = str(uuid.uuid4())
    p3 = str(uuid.uuid4())

    forum_id = str(uuid.uuid4())
    author1 = str(uuid.uuid4())
    author2 = str(uuid.uuid4())

    mock_mongo.insert_many(
        [
            {
                "_id": p1,
                "title": "Scaling Distributed Caches",
                "body": "When scaling Redis clusters across multiple availability zones...",
                "image": "https://cdn.example.com/posts/p1.png",
                "author_profile_id": author1,
                "author_display_name": "Alice Architect",
                "author_avatar": "https://cdn.example.com/avatars/a1.png",
                "forum_id": forum_id,
                "forum_title": "Backend Engineering",
                "forum_slug": "backend-eng",
                "upvotes_count": 50,
                "downvotes_count": 2,
                "popularity_score": 48,
                "comments_count": 12,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=2),
            },
            {
                "_id": p2,
                "title": "Solo Profile Reflections",
                "body": "Thoughts on software craftsmanship and domain-driven design...",
                "image": None,
                "author_profile_id": author2,
                "author_display_name": "Bob Builder",
                "author_avatar": None,
                "forum_id": None,  # Profile post
                "upvotes_count": 80,
                "downvotes_count": 5,
                "popularity_score": 75,
                "comments_count": 20,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=5),
            },
            {
                "_id": p3,
                "title": "Modern Python Type Checking",
                "body": "Using msgspec and mypy strictly in modern Python applications...",
                "image": None,
                "author_profile_id": author1,
                "author_display_name": "Alice Architect",
                "forum_id": forum_id,
                "forum_title": "Backend Engineering",
                "forum_slug": "backend-eng",
                "upvotes_count": 20,
                "downvotes_count": 1,
                "popularity_score": 19,
                "comments_count": 4,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=8),
            },
        ]
    )

    # Populate Redis Sorted Set: p2 (75.0) > p1 (48.0) > p3 (19.0)
    mock_redis.zadd(REDIS_KEY_POPULAR_24H_GLOBAL, {p2: 75.0, p1: 48.0, p3: 19.0})

    return {"p1": p1, "p2": p2, "p3": p3, "forum_id": forum_id, "author1": author1}


def test_explore_popular_feed_served_from_redis(
    client: DMRClient, sample_feed_posts, mock_mongo, mock_redis
):
    """Test GET /api/v1/feeds/explore/?sort=popular returns Redis sorted order."""
    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        response = client.get("/api/v1/feeds/explore/?sort=popular&timeframe=day")

    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    items = data["data"]
    assert len(items) == 3

    # Ranking must match Redis ZSET: p2 -> p1 -> p3
    assert items[0]["id"] == sample_feed_posts["p2"]
    assert items[0]["metrics"]["popularity_score"] == 75
    assert items[0]["forum"] is None  # Profile post

    assert items[1]["id"] == sample_feed_posts["p1"]
    assert items[1]["metrics"]["popularity_score"] == 48
    assert items[1]["forum"]["slug"] == "backend-eng"

    assert items[2]["id"] == sample_feed_posts["p3"]
    assert items[2]["metrics"]["popularity_score"] == 19


def test_explore_feed_source_filtering(
    client: DMRClient, sample_feed_posts, mock_mongo, mock_redis
):
    """Test source=forums_only and source=profiles_only query filters."""
    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        # 1. Forums only
        resp_forums = client.get("/api/v1/feeds/explore/?sort=popular&source=forums_only")
        assert resp_forums.status_code == 200
        items_f = resp_forums.json()["data"]
        assert len(items_f) == 2
        for it in items_f:
            assert it["forum"] is not None

        # 2. Profiles only
        resp_profiles = client.get("/api/v1/feeds/explore/?sort=popular&source=profiles_only")
        assert resp_profiles.status_code == 200
        items_p = resp_profiles.json()["data"]
        assert len(items_p) == 1
        assert items_p[0]["id"] == sample_feed_posts["p2"]
        assert items_p[0]["forum"] is None


def test_explore_feed_keyset_pagination(
    client: DMRClient, sample_feed_posts, mock_mongo, mock_redis
):
    """Test Keyset Cursor Pagination on explore feed."""
    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        # Page 1: limit 2
        page1_resp = client.get("/api/v1/feeds/explore/?sort=popular&limit=2")
        assert page1_resp.status_code == 200
        p1_data = page1_resp.json()
        assert len(p1_data["data"]) == 2
        assert p1_data["pagination"]["has_more"] is True
        cursor = p1_data["pagination"]["next_cursor"]
        assert cursor is not None

        # Page 2: with cursor
        page2_resp = client.get(f"/api/v1/feeds/explore/?sort=popular&limit=2&cursor={cursor}")
        assert page2_resp.status_code == 200
        p2_data = page2_resp.json()
        assert len(p2_data["data"]) == 1
        assert p2_data["data"][0]["id"] == sample_feed_posts["p3"]
        assert p2_data["pagination"]["has_more"] is False


def test_explore_recent_feed(client: DMRClient, sample_feed_posts, mock_mongo, mock_redis):
    """Test GET /api/v1/feeds/explore/?sort=recent orders by recency."""
    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        response = client.get("/api/v1/feeds/explore/?sort=recent")

    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 3
    # p1 (2h ago) -> p2 (5h ago) -> p3 (8h ago)
    assert items[0]["id"] == sample_feed_posts["p1"]
    assert items[1]["id"] == sample_feed_posts["p2"]
    assert items[2]["id"] == sample_feed_posts["p3"]


@pytest.mark.django_db
def test_explore_feed_with_user_context(
    client: DMRClient, sample_feed_posts, mock_mongo, mock_redis, auth_headers, profile_id
):
    """Test that authenticated user gets their personal vote context reflected."""
    # Cast a vote in DB for user on p1
    p1 = sample_feed_posts["p1"]
    Vote.objects.create(
        user_profile_id=profile_id,
        target_type=TargetType.POST,
        target_id=uuid.UUID(p1),
        value=VoteValue.UPVOTE,
    )

    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        response = client.get(
            "/api/v1/feeds/explore/?sort=popular",
            **auth_headers,
        )

    assert response.status_code == 200
    items = response.json()["data"]
    item_p1 = next(it for it in items if it["id"] == p1)
    assert item_p1["user_context"]["voted"] == 1

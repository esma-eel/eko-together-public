"""Tests for Joined Forums and Personalized Following feeds."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from dmr.test import DMRClient


@pytest.fixture
def scoped_feed_data(mock_mongo):
    """Seed test data for forums and following feeds."""
    now = datetime.now(tz=UTC)
    f1 = str(uuid.uuid4())
    f2 = str(uuid.uuid4())

    creator1 = str(uuid.uuid4())
    creator2 = str(uuid.uuid4())

    p_f1 = str(uuid.uuid4())
    p_f2 = str(uuid.uuid4())
    p_c1 = str(uuid.uuid4())
    p_c2 = str(uuid.uuid4())

    mock_mongo.insert_many(
        [
            {
                "_id": p_f1,
                "title": "Forum 1 Discussion",
                "body": "Content in forum 1",
                "forum_id": f1,
                "author_profile_id": creator1,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=1),
            },
            {
                "_id": p_f2,
                "title": "Forum 2 Discussion",
                "body": "Content in forum 2",
                "forum_id": f2,
                "author_profile_id": creator2,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=2),
            },
            {
                "_id": p_c1,
                "title": "Creator 1 Personal Update",
                "body": "Personal thoughts from creator 1",
                "forum_id": None,
                "author_profile_id": creator1,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=3),
            },
            {
                "_id": p_c2,
                "title": "Creator 2 Personal Update",
                "body": "Personal thoughts from creator 2",
                "forum_id": None,
                "author_profile_id": creator2,
                "visibility": "PUBLIC",
                "is_deleted": False,
                "is_archived": False,
                "created_at": now - timedelta(hours=4),
            },
        ]
    )

    return {
        "f1": f1,
        "f2": f2,
        "creator1": creator1,
        "creator2": creator2,
        "p_f1": p_f1,
        "p_f2": p_f2,
        "p_c1": p_c1,
        "p_c2": p_c2,
    }


def test_forums_feed_requires_auth(client: DMRClient):
    """Test GET /api/v1/feeds/forums/ rejects unauthenticated requests."""
    response = client.get("/api/v1/feeds/forums/")
    assert response.status_code == 401


def test_forums_feed_scoping(client: DMRClient, auth_headers, scoped_feed_data, mock_mongo):
    """Test that joined forums feed strictly returns posts from joined forums."""
    # User has joined only f1
    joined = [scoped_feed_data["f1"]]

    with patch(
        "services.feed_service.apps.feed.controllers.get_joined_forums_feed"
    ) as mock_get_feed:
        from services.feed_service.apps.feed.services import get_joined_forums_feed

        def call_with_joined(query, user_profile_id):
            return get_joined_forums_feed(query, user_profile_id, joined_forum_ids=joined)

        mock_get_feed.side_effect = call_with_joined

        with patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ):
            response = client.get("/api/v1/feeds/forums/", **auth_headers)

    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == scoped_feed_data["p_f1"]


def test_following_feed_requires_auth(client: DMRClient):
    """Test GET /api/v1/feeds/following/ rejects unauthenticated requests."""
    response = client.get("/api/v1/feeds/following/")
    assert response.status_code == 401


def test_following_feed_scoping(client: DMRClient, auth_headers, scoped_feed_data, mock_mongo):
    """Test that following feed strictly returns profile posts from followed creators."""
    # User follows only creator1
    followed = [scoped_feed_data["creator1"]]

    with patch("services.feed_service.apps.feed.controllers.get_following_feed") as mock_get_feed:
        from services.feed_service.apps.feed.services import get_following_feed

        def call_with_followed(query, user_profile_id):
            return get_following_feed(query, user_profile_id, followed_profile_ids=followed)

        mock_get_feed.side_effect = call_with_followed

        with patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ):
            response = client.get("/api/v1/feeds/following/", **auth_headers)

    assert response.status_code == 200
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == scoped_feed_data["p_c1"]


def test_feed_health_endpoint(client: DMRClient, mock_redis, mock_mongo):
    """Test GET /api/v1/feeds/health/ endpoint returns structured health report."""
    with (
        patch(
            "services.feed_service.apps.feed.controllers.get_redis_client", return_value=mock_redis
        ),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        response = client.get("/api/v1/feeds/health/")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "feed_service"
    assert data["redis"] == "ok"
    assert "timestamp" in data

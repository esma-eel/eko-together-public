"""Unit and integration tests for CQRS 24-hour sliding window calculation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection

from services.feed_service.apps.feed.services import (
    REDIS_KEY_POPULAR_24H_GLOBAL,
    compute_24h_sliding_window,
)
from services.voting_service.apps.votes.models import TargetType, Vote, VoteValue


@pytest.mark.django_db
def test_sliding_window_computation(mock_redis, mock_mongo):
    """Test 24-hour rolling aggregation from Voting DB into Redis."""
    now = datetime.now(tz=UTC)
    p1 = str(uuid.uuid4())
    p2 = str(uuid.uuid4())
    p3 = str(uuid.uuid4())
    p4_deleted = str(uuid.uuid4())
    p5 = str(uuid.uuid4())

    # Populate active MongoDB posts
    mock_mongo.insert_many(
        [
            {"_id": p1, "title": "Post 1", "body": "B1", "is_deleted": False, "is_archived": False},
            {"_id": p2, "title": "Post 2", "body": "B2", "is_deleted": False, "is_archived": False},
            {"_id": p3, "title": "Post 3", "body": "B3", "is_deleted": False, "is_archived": False},
            {
                "_id": p4_deleted,
                "title": "Deleted Post",
                "body": "B4",
                "is_deleted": True,
                "is_archived": False,
            },
            {"_id": p5, "title": "Post 5", "body": "B5", "is_deleted": False, "is_archived": False},
        ]
    )

    # Populate Votes:
    # Post 1: 3 upvotes in last 24h -> Net +3
    for _ in range(3):
        Vote.objects.create(
            user_profile_id=uuid.uuid4(),
            target_type=TargetType.POST,
            target_id=uuid.UUID(p1),
            value=VoteValue.UPVOTE,
        )

    # Post 2: 1 upvote, 2 downvotes in last 24h -> Net -1 (negative, should be excluded)
    Vote.objects.create(
        user_profile_id=uuid.uuid4(),
        target_type=TargetType.POST,
        target_id=uuid.UUID(p2),
        value=VoteValue.UPVOTE,
    )
    for _ in range(2):
        Vote.objects.create(
            user_profile_id=uuid.uuid4(),
            target_type=TargetType.POST,
            target_id=uuid.UUID(p2),
            value=VoteValue.DOWNVOTE,
        )

    # Post 3: 5 upvotes created 2 days ago (older than 24h) -> should be excluded
    old_time = now - timedelta(days=2)
    with connection.cursor() as cursor:
        for _ in range(5):
            cursor.execute(
                """
                INSERT INTO votes (
                    id, user_profile_id, target_type, target_id, value, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    str(uuid.uuid4()),
                    str(uuid.uuid4()),
                    TargetType.POST,
                    p3,
                    VoteValue.UPVOTE,
                    old_time.isoformat(),
                    old_time.isoformat(),
                ],
            )

    # Post 4: 2 upvotes in last 24h, BUT post is deleted in Mongo -> should be excluded
    for _ in range(2):
        Vote.objects.create(
            user_profile_id=uuid.uuid4(),
            target_type=TargetType.POST,
            target_id=uuid.UUID(p4_deleted),
            value=VoteValue.UPVOTE,
        )

    # Post 5: 4 upvotes in last 24h -> Net +4
    for _ in range(4):
        Vote.objects.create(
            user_profile_id=uuid.uuid4(),
            target_type=TargetType.POST,
            target_id=uuid.UUID(p5),
            value=VoteValue.UPVOTE,
        )

    # Run the CQRS computation
    with patch(
        "services.feed_service.apps.feed.services.get_mongo_posts_collection",
        return_value=mock_mongo,
    ):
        result = compute_24h_sliding_window(
            redis_client=mock_redis,
            voting_db_alias="default",
        )

    assert result["status"] == "success"
    assert result["posts_ranked"] == 2

    # Verify Redis ZSET
    ranked = mock_redis.zrevrange(REDIS_KEY_POPULAR_24H_GLOBAL, 0, -1, withscores=True)
    assert len(ranked) == 2
    assert ranked[0][0] == p5
    assert ranked[0][1] == 4.0
    assert ranked[1][0] == p1
    assert ranked[1][1] == 3.0

    # Ensure excluded posts are NOT in the set
    all_members = [r[0] for r in ranked]
    assert p2 not in all_members
    assert p3 not in all_members
    assert p4_deleted not in all_members


@pytest.mark.django_db
def test_sliding_window_empty_votes(mock_redis, mock_mongo):
    """Test sliding window when no votes exist at all."""
    with patch(
        "services.feed_service.apps.feed.services.get_mongo_posts_collection",
        return_value=mock_mongo,
    ):
        result = compute_24h_sliding_window(
            redis_client=mock_redis,
            voting_db_alias="default",
        )

    assert result["status"] == "success"
    assert result["posts_ranked"] == 0
    ranked = mock_redis.zrevrange(REDIS_KEY_POPULAR_24H_GLOBAL, 0, -1)
    assert len(ranked) == 0


@pytest.mark.django_db
def test_management_command_execution(mock_redis, mock_mongo):
    """Test compute_sliding_window_feed management command runs without errors."""
    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch(
            "services.feed_service.apps.feed.services.get_mongo_posts_collection",
            return_value=mock_mongo,
        ),
    ):
        call_command("compute_sliding_window_feed", "--once")

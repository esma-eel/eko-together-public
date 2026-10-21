"""Tests for RabbitMQ Vote Event Consumer Worker and MongoDB Counter Ingestion."""

from __future__ import annotations

from uuid import UUID

import pytest

from services.post_comment_service.db import (
    get_comments_collection,
    get_posts_collection,
)
from services.post_comment_service.workers.vote_consumer import (
    process_vote_event_message,
    update_target_counters,
)
from shared.events import (
    VoteCastEvent,
    VoteRevokedEvent,
    serialize_event,
)

pytestmark = pytest.mark.django_db


def test_update_target_counters_post(sample_post_id: UUID):
    """Directly updating post document with $inc modifies upvotes and popularity score."""
    success = update_target_counters(
        target_type="POST",
        target_id=sample_post_id,
        delta_up=1,
        delta_down=0,
        net_delta=1,
    )
    assert success is True

    doc = get_posts_collection().find_one({"_id": str(sample_post_id)})
    assert doc is not None
    assert doc["upvotes_count"] == 1
    assert doc["downvotes_count"] == 0
    assert doc["popularity_score"] == 1


def test_update_target_counters_comment(sample_comment_id: UUID):
    """Directly updating comment document with $inc modifies counters."""
    success = update_target_counters(
        target_type="COMMENT",
        target_id=sample_comment_id,
        delta_up=0,
        delta_down=1,
        net_delta=-1,
    )
    assert success is True

    doc = get_comments_collection().find_one({"_id": str(sample_comment_id)})
    assert doc is not None
    assert doc["upvotes_count"] == 0
    assert doc["downvotes_count"] == 1
    assert doc["popularity_score"] == -1


def test_process_vote_cast_event(sample_post_id: UUID, voter_profile_id: UUID):
    """Consumer parses serialized VoteCastEvent and increments post counters."""
    event = VoteCastEvent(
        target_type="POST",
        target_id=sample_post_id,
        user_profile_id=voter_profile_id,
        delta_up=1,
        delta_down=0,
        net_delta=1,
    )
    payload_bytes = serialize_event(event)

    handled = process_vote_event_message(payload_bytes)
    assert handled is True

    doc = get_posts_collection().find_one({"_id": str(sample_post_id)})
    assert doc["upvotes_count"] == 1
    assert doc["popularity_score"] == 1


def test_process_vote_flip_event(sample_post_id: UUID, voter_profile_id: UUID):
    """Flipping from +1 to -1 applies delta_up: -1, delta_down: 1, net_delta: -2."""
    # First vote: +1
    event_1 = VoteCastEvent(
        target_type="POST",
        target_id=sample_post_id,
        user_profile_id=voter_profile_id,
        delta_up=1,
        delta_down=0,
        net_delta=1,
    )
    process_vote_event_message(serialize_event(event_1))

    # Flip vote: -1 (delta_up=-1, delta_down=1, net_delta=-2)
    event_flip = VoteCastEvent(
        target_type="POST",
        target_id=sample_post_id,
        user_profile_id=voter_profile_id,
        delta_up=-1,
        delta_down=1,
        net_delta=-2,
    )
    handled = process_vote_event_message(serialize_event(event_flip))
    assert handled is True

    doc = get_posts_collection().find_one({"_id": str(sample_post_id)})
    assert doc["upvotes_count"] == 0
    assert doc["downvotes_count"] == 1
    assert doc["popularity_score"] == -1


def test_process_vote_revoked_event(sample_post_id: UUID, voter_profile_id: UUID):
    """Revoking an upvote decrements upvotes and popularity score by 1."""
    # First cast upvote
    cast_ev = VoteCastEvent(
        target_type="POST",
        target_id=sample_post_id,
        user_profile_id=voter_profile_id,
        delta_up=1,
        delta_down=0,
        net_delta=1,
    )
    process_vote_event_message(serialize_event(cast_ev))

    # Revoke vote
    rev_ev = VoteRevokedEvent(
        target_type="POST",
        target_id=sample_post_id,
        user_profile_id=voter_profile_id,
        previous_value=1,
    )
    handled = process_vote_event_message(serialize_event(rev_ev))
    assert handled is True

    doc = get_posts_collection().find_one({"_id": str(sample_post_id)})
    assert doc["upvotes_count"] == 0
    assert doc["downvotes_count"] == 0
    assert doc["popularity_score"] == 0

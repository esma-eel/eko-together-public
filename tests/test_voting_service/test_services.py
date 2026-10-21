"""Tests for Voting Service business logic and event emissions."""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from services.voting_service.apps.votes.models import Vote
from services.voting_service.apps.votes.services import (
    cast_or_toggle_vote,
    get_user_vote_status,
)
from shared.events import (
    ROUTING_VOTE_CAST,
    ROUTING_VOTE_REVOKED,
    VoteCastEvent,
    VoteRevokedEvent,
)
from shared.exceptions.base import (
    EntityNotFoundException,
    ValidationException,
)


@pytest.mark.django_db
def test_cast_new_upvote(
    sample_post_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Casting an upvote on a post creates a vote record and emits VoteCastEvent."""
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=1,
    )
    assert res.target_id == str(sample_post_id)
    assert res.target_type == "POST"
    assert res.user_vote == 1
    assert res.upvotes_count == 1
    assert res.downvotes_count == 0
    assert res.popularity_score == 1

    # Verify event emission
    assert len(captured_events) == 1
    event, key = captured_events[0]
    assert isinstance(event, VoteCastEvent)
    assert key == ROUTING_VOTE_CAST
    assert event.target_id == sample_post_id
    assert event.delta_up == 1
    assert event.delta_down == 0
    assert event.net_delta == 1


@pytest.mark.django_db
def test_cast_new_downvote(
    sample_post_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Casting a downvote creates a vote record with -1 and emits VoteCastEvent."""
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=-1,
    )
    assert res.user_vote == -1
    assert res.upvotes_count == 0
    assert res.downvotes_count == 1
    assert res.popularity_score == -1

    assert len(captured_events) == 1
    event, key = captured_events[0]
    assert isinstance(event, VoteCastEvent)
    assert key == ROUTING_VOTE_CAST
    assert event.delta_up == 0
    assert event.delta_down == 1
    assert event.net_delta == -1


@pytest.mark.django_db
def test_flip_vote_from_upvote_to_downvote(
    sample_post_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Flipping vote from +1 to -1 updates DB with delta -2 and emits VoteCastEvent."""
    cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=1,
    )
    captured_events.clear()

    # Flip to -1
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=-1,
    )
    assert res.user_vote == -1
    assert res.upvotes_count == 0
    assert res.downvotes_count == 1
    assert res.popularity_score == -1

    assert len(captured_events) == 1
    event, key = captured_events[0]
    assert isinstance(event, VoteCastEvent)
    assert key == ROUTING_VOTE_CAST
    assert event.delta_up == -1
    assert event.delta_down == 1
    assert event.net_delta == -2


@pytest.mark.django_db
def test_flip_vote_from_downvote_to_upvote(
    sample_post_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Flipping vote from -1 to +1 updates DB with delta +2 and emits VoteCastEvent."""
    cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=-1,
    )
    captured_events.clear()

    # Flip to +1
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=1,
    )
    assert res.user_vote == 1
    assert res.upvotes_count == 1
    assert res.downvotes_count == 0
    assert res.popularity_score == 1

    assert len(captured_events) == 1
    event, key = captured_events[0]
    assert isinstance(event, VoteCastEvent)
    assert event.delta_up == 1
    assert event.delta_down == -1
    assert event.net_delta == 2


@pytest.mark.django_db
def test_toggle_off_vote(
    sample_post_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Voting +1 again when already +1 toggles the vote off and emits VoteRevokedEvent."""
    cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=1,
    )
    captured_events.clear()

    # Vote 1 again -> toggle off
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=1,
    )
    assert res.user_vote is None
    assert res.upvotes_count == 0
    assert res.downvotes_count == 0
    assert res.popularity_score == 0
    assert Vote.objects.filter(target_id=sample_post_id).count() == 0

    assert len(captured_events) == 1
    event, key = captured_events[0]
    assert isinstance(event, VoteRevokedEvent)
    assert key == ROUTING_VOTE_REVOKED
    assert event.previous_value == 1


@pytest.mark.django_db
def test_explicit_remove_vote_with_zero(
    sample_post_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Sending value: 0 removes existing vote."""
    cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=-1,
    )
    captured_events.clear()

    # Clear vote with 0
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=0,
    )
    assert res.user_vote is None
    assert res.downvotes_count == 0

    assert len(captured_events) == 1
    event, key = captured_events[0]
    assert isinstance(event, VoteRevokedEvent)
    assert event.previous_value == -1


@pytest.mark.django_db
def test_comment_voting(
    sample_comment_id: UUID,
    voter_profile_id: UUID,
    captured_events: list,
):
    """Voting on a comment target succeeds and aggregates correctly."""
    res = cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="COMMENT",
        target_id=sample_comment_id,
        value=1,
    )
    assert res.target_type == "COMMENT"
    assert res.user_vote == 1
    assert res.upvotes_count == 1
    assert len(captured_events) == 1
    assert captured_events[0][0].target_type == "COMMENT"


@pytest.mark.django_db
def test_nonexistent_target_raises_404(
    voter_profile_id: UUID,
):
    """Voting on a nonexistent post UUID raises EntityNotFoundException."""
    non_existent = uuid.uuid4()
    with pytest.raises(EntityNotFoundException):
        cast_or_toggle_vote(
            user_profile_id=voter_profile_id,
            target_type="POST",
            target_id=non_existent,
            value=1,
        )


@pytest.mark.django_db
def test_invalid_vote_value_raises_validation_error(
    sample_post_id: UUID,
    voter_profile_id: UUID,
):
    """Sending a value other than 1, -1, 0 raises ValidationException."""
    with pytest.raises(ValidationException):
        cast_or_toggle_vote(
            user_profile_id=voter_profile_id,
            target_type="POST",
            target_id=sample_post_id,
            value=5,
        )


@pytest.mark.django_db
def test_get_user_vote_status(
    sample_post_id: UUID,
    voter_profile_id: UUID,
):
    """get_user_vote_status accurately reflects voter's state."""
    # Before voting
    status_1 = get_user_vote_status(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
    )
    assert status_1.user_vote is None

    # Cast vote
    cast_or_toggle_vote(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
        value=1,
    )

    # After voting
    status_2 = get_user_vote_status(
        user_profile_id=voter_profile_id,
        target_type="POST",
        target_id=sample_post_id,
    )
    assert status_2.user_vote == 1

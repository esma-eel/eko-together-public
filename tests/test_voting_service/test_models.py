"""Tests for Vote ORM model constraints and indexing."""

from __future__ import annotations

import uuid
import pytest
from django.db import IntegrityError, transaction
from services.voting_service.apps.votes.models import Vote, TargetType, VoteValue


@pytest.mark.django_db
def test_vote_creation_success():
    """Verify vote record is created with valid fields."""
    user_id = uuid.uuid4()
    target_id = uuid.uuid4()

    vote = Vote.objects.create(
        user_profile_id=user_id,
        target_type=TargetType.POST,
        target_id=target_id,
        value=VoteValue.UPVOTE,
    )
    assert vote.pk is not None
    assert vote.value == 1
    assert vote.created_at is not None
    assert vote.updated_at is not None
    assert str(target_id) in str(vote)


@pytest.mark.django_db
def test_unique_user_target_vote_constraint():
    """Enforce compound unique constraint on (user_profile_id, target_type, target_id)."""
    user_id = uuid.uuid4()
    target_id = uuid.uuid4()

    Vote.objects.create(
        user_profile_id=user_id,
        target_type=TargetType.POST,
        target_id=target_id,
        value=VoteValue.UPVOTE,
    )

    with transaction.atomic(), pytest.raises(IntegrityError):
        Vote.objects.create(
            user_profile_id=user_id,
            target_type=TargetType.POST,
            target_id=target_id,
            value=VoteValue.DOWNVOTE,
        )


@pytest.mark.django_db
def test_same_user_can_vote_on_different_targets():
    """Verify user can vote on distinct posts or comments without conflict."""
    user_id = uuid.uuid4()
    post_1 = uuid.uuid4()
    post_2 = uuid.uuid4()

    v1 = Vote.objects.create(
        user_profile_id=user_id,
        target_type=TargetType.POST,
        target_id=post_1,
        value=VoteValue.UPVOTE,
    )
    v2 = Vote.objects.create(
        user_profile_id=user_id,
        target_type=TargetType.POST,
        target_id=post_2,
        value=VoteValue.DOWNVOTE,
    )
    assert v1.pk != v2.pk
    assert Vote.objects.filter(user_profile_id=user_id).count() == 2

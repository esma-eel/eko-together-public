"""Service layer for Voting Service.

Encapsulates voting business logic, atomic state toggling/flipping,
count aggregations, and asynchronous event emission to RabbitMQ.
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from django.db import models, transaction

from services.post_comment_service.db import (
    get_comments_collection,
    get_posts_collection,
)
from services.voting_service.apps.votes.models import TargetType, Vote, VoteValue
from services.voting_service.apps.votes.schemas import (
    UserVoteStatusSchema,
    VoteResultDataSchema,
)
from shared.events import (
    ROUTING_VOTE_CAST,
    ROUTING_VOTE_REVOKED,
    VoteCastEvent,
    VoteRevokedEvent,
    publish_domain_event,
)
from shared.exceptions.base import (
    EntityNotFoundException,
    ValidationException,
)

logger = logging.getLogger(__name__)


def verify_target_exists(target_type: Literal["POST", "COMMENT"], target_id: UUID) -> None:
    """Verify target entity exists and is not soft-deleted in MongoDB."""
    target_id_str = str(target_id)
    if target_type == "POST":
        posts = get_posts_collection()
        doc = posts.find_one({"_id": target_id_str, "is_deleted": {"$ne": True}})
        if not doc:
            raise EntityNotFoundException("Target entity not found.")
    elif target_type == "COMMENT":
        comments = get_comments_collection()
        doc = comments.find_one({"_id": target_id_str, "is_deleted": {"$ne": True}})
        if not doc:
            raise EntityNotFoundException("Target entity not found.")
    else:
        raise ValidationException(f"Unsupported target type: {target_type}")


def cast_or_toggle_vote(
    *,
    user_profile_id: UUID,
    target_type: Literal["POST", "COMMENT"],
    target_id: UUID,
    value: int,
) -> VoteResultDataSchema:
    """Atomically cast, toggle, or revoke a vote on a target entity.

    Rules:
      - value must be 1, -1, or 0.
      - If value is 0, or equals existing vote value: toggle off / revoke.
      - If no existing vote: create new vote (+1 or -1).
      - If existing vote has opposite value: flip vote (+1 -> -1 or -1 -> +1).
      - After DB commit, publish VoteCastEvent or VoteRevokedEvent to RabbitMQ.
    """
    if value not in (-1, 0, 1):
        raise ValidationException("Vote value must be 1 (Upvote), -1 (Downvote), or 0 (Remove).")

    # 1. Verify target exists in document store
    verify_target_exists(target_type, target_id)

    event_to_publish = None
    routing_key_to_use = None

    # 2. Atomic state transition in dedicated Voting DB
    with transaction.atomic():
        existing_vote = (
            Vote.objects.select_for_update()
            .filter(
                user_profile_id=user_profile_id,
                target_type=target_type,
                target_id=target_id,
            )
            .first()
        )

        user_vote: int | None = None

        if value == 0 or (existing_vote and existing_vote.value == value):
            # Toggle off / revoke existing vote
            if existing_vote:
                prev_val = existing_vote.value
                existing_vote.delete()
                user_vote = None

                event_to_publish = VoteRevokedEvent(
                    target_type=target_type,
                    target_id=target_id,
                    user_profile_id=user_profile_id,
                    previous_value=prev_val,
                )
                routing_key_to_use = ROUTING_VOTE_REVOKED
            else:
                user_vote = None

        elif existing_vote is None:
            # Brand new vote
            Vote.objects.create(
                user_profile_id=user_profile_id,
                target_type=target_type,
                target_id=target_id,
                value=value,
            )
            user_vote = value

            delta_up = 1 if value == 1 else 0
            delta_down = 1 if value == -1 else 0
            net_delta = 1 if value == 1 else -1

            event_to_publish = VoteCastEvent(
                target_type=target_type,
                target_id=target_id,
                user_profile_id=user_profile_id,
                delta_up=delta_up,
                delta_down=delta_down,
                net_delta=net_delta,
            )
            routing_key_to_use = ROUTING_VOTE_CAST

        else:
            # Flip existing vote (+1 to -1 or -1 to +1)
            existing_vote.value = value
            existing_vote.save(update_fields=["value", "updated_at"])
            user_vote = value

            delta_up = -1 if value == -1 else 1
            delta_down = 1 if value == -1 else -1
            net_delta = -2 if value == -1 else 2

            event_to_publish = VoteCastEvent(
                target_type=target_type,
                target_id=target_id,
                user_profile_id=user_profile_id,
                delta_up=delta_up,
                delta_down=delta_down,
                net_delta=net_delta,
            )
            routing_key_to_use = ROUTING_VOTE_CAST

        # 3. Exact count aggregation from dedicated Voting DB
        counts = Vote.objects.filter(
            target_type=target_type,
            target_id=target_id,
        ).aggregate(
            up=models.Count("id", filter=models.Q(value=VoteValue.UPVOTE)),
            down=models.Count("id", filter=models.Q(value=VoteValue.DOWNVOTE)),
        )

        upvotes_count = counts["up"] or 0
        downvotes_count = counts["down"] or 0
        popularity_score = upvotes_count - downvotes_count

    # 4. Asynchronously publish event to RabbitMQ buffer
    if event_to_publish and routing_key_to_use:
        publish_domain_event(event_to_publish, routing_key=routing_key_to_use)

    return VoteResultDataSchema(
        target_id=str(target_id),
        target_type=target_type,
        user_vote=user_vote,
        upvotes_count=upvotes_count,
        downvotes_count=downvotes_count,
        popularity_score=popularity_score,
    )


def get_user_vote_status(
    *,
    user_profile_id: UUID,
    target_type: Literal["POST", "COMMENT"],
    target_id: UUID,
) -> UserVoteStatusSchema:
    """Fetch active vote status of the current user for a given target entity."""
    verify_target_exists(target_type, target_id)

    vote = Vote.objects.filter(
        user_profile_id=user_profile_id,
        target_type=target_type,
        target_id=target_id,
    ).first()

    user_vote = vote.value if vote else None

    return UserVoteStatusSchema(
        target_id=str(target_id),
        target_type=target_type,
        user_vote=user_vote,
    )

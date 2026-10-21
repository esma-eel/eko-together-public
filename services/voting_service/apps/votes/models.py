"""Vote model for dedicated Voting Service.

Enforces composite unique constraint on (user_profile_id, target_type, target_id)
and provides indexing optimized for fast counts and rolling 24-hour CQRS aggregation.
"""

from __future__ import annotations

import uuid

from django.db import models


class TargetType(models.TextChoices):
    """Supported voting targets."""

    POST = "POST", "Post"
    COMMENT = "COMMENT", "Comment"


class VoteValue(models.IntegerChoices):
    """Vote value choices."""

    UPVOTE = 1, "Upvote"
    DOWNVOTE = -1, "Downvote"


class Vote(models.Model):
    """Atomic vote record stored in dedicated Voting PostgreSQL DB.

    Zero Content Foreign Keys: target_id is a decoupled UUID pointing to
    either a MongoDB Post or Comment.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_profile_id = models.UUIDField(db_index=True, help_text="Voter user profile UUID")
    target_type = models.CharField(
        max_length=10,
        choices=TargetType.choices,
        help_text="Target entity type (POST or COMMENT)",
    )
    target_id = models.UUIDField(db_index=True, help_text="Target entity UUID")
    value = models.SmallIntegerField(
        choices=VoteValue.choices,
        help_text="+1 for Upvote, -1 for Downvote",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="Timestamp used for rolling 24-hour popular feed CQRS queries",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "votes"
        verbose_name = "Vote"
        verbose_name_plural = "Votes"
        constraints = [
            models.UniqueConstraint(
                fields=["user_profile_id", "target_type", "target_id"],
                name="unique_user_target_vote",
            ),
        ]
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="idx_vote_target"),
            models.Index(
                fields=["target_type", "target_id", "value"],
                name="idx_vote_target_val",
            ),
            models.Index(fields=["created_at"], name="idx_vote_created_at"),
        ]

    def __str__(self) -> str:
        return f"Vote({self.user_profile_id} -> {self.target_type}:{self.target_id} = {self.value})"

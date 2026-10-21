"""Typed DTO Schemas for Voting Service using msgspec."""

from __future__ import annotations

import msgspec

# ============================================================================
# Path Parameters
# ============================================================================


class PostVotePathSchema(msgspec.Struct, kw_only=True):
    """Path parameter for post-scoped vote endpoints."""

    post_id: str


class CommentVotePathSchema(msgspec.Struct, kw_only=True):
    """Path parameter for comment-scoped vote endpoints."""

    comment_id: str


# ============================================================================
# Request Body
# ============================================================================


class VoteInputSchema(msgspec.Struct, kw_only=True):
    """Payload for casting, toggling, or removing a vote.

    value: 1 (Upvote), -1 (Downvote), 0 (Explicitly remove vote)
    """

    value: int


# ============================================================================
# Response Payloads
# ============================================================================


class VoteResultDataSchema(msgspec.Struct, kw_only=True):
    """Target voting state after vote action."""

    target_id: str
    target_type: str  # POST or COMMENT
    user_vote: int | None  # 1, -1, or None (if revoked)
    upvotes_count: int
    downvotes_count: int
    popularity_score: int


class VoteResponseSchema(msgspec.Struct, kw_only=True):
    """Standard unified response wrapper for voting actions."""

    status: str = "success"
    data: VoteResultDataSchema


class UserVoteStatusSchema(msgspec.Struct, kw_only=True):
    """Current authenticated user's vote status for a target."""

    target_id: str
    target_type: str
    user_vote: int | None


class UserVoteResponseSchema(msgspec.Struct, kw_only=True):
    """Standard response wrapper for user vote status."""

    status: str = "success"
    data: UserVoteStatusSchema

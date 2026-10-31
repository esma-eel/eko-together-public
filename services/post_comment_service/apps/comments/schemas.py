"""Typed DTO Schemas for Comment Service.

Built using high-performance msgspec.Struct for instantaneous validation
and serialization.
"""

from __future__ import annotations

import msgspec

# ============================================================================
# Path & Query Schemas
# ============================================================================


class CommentIdPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for comment ID resolution."""

    comment_id: str


class PostCommentPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for comments under a post."""

    post_id: str


class CommentListQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for listing comments on a post."""

    ordering: str = "newest"  # popular | newest | oldest
    page: int = 1
    page_size: int = 20


# ============================================================================
# Request Body Schemas
# ============================================================================


class CommentCreateSchema(msgspec.Struct, kw_only=True):
    """Payload for creating a root comment on a post."""

    body: str


class CommentReplySchema(msgspec.Struct, kw_only=True):
    """Payload for replying to an existing comment (depth enforced ≤ 3)."""

    body: str


class CommentUpdateSchema(msgspec.Struct, kw_only=True):
    """Payload for editing comment text (author only)."""

    body: str


class ArchiveCommentSchema(msgspec.Struct, kw_only=True):
    """Payload for archiving/locking a comment thread (forum admin only)."""

    is_archived: bool


class CommentVoteSchema(msgspec.Struct, kw_only=True):
    """Payload for casting a vote on a comment.

    value: 1 (upvote), -1 (downvote), 0 (remove vote)
    """

    value: int  # Constrained to [-1, 0, 1] in service layer


# ============================================================================
# Response Schemas
# ============================================================================


class AuthorMiniSchema(msgspec.Struct, kw_only=True):
    """Minimal author info embedded in comment responses."""

    id: str | None
    display_name: str | None
    avatar: str | None


class CommentResponseSchema(msgspec.Struct, kw_only=True):
    """Full serialized representation of a comment (with nested replies)."""

    id: str
    post_id: str
    parent_id: str | None
    depth: int
    author: AuthorMiniSchema
    body: str
    upvotes_count: int
    downvotes_count: int
    popularity_score: int
    user_vote: int | None
    is_archived: bool
    is_deleted: bool
    replies_count: int
    replies: list[CommentResponseSchema]
    created_at: str
    updated_at: str


# Resolve the forward reference for recursive replies field
CommentResponseSchema.__annotations__  # noqa: B018


class CommentListResponseSchema(msgspec.Struct, kw_only=True):
    """Paginated list of root comments with nested replies."""

    count: int
    next: str | None
    previous: str | None
    results: list[CommentResponseSchema]


class CommentVoteResponseSchema(msgspec.Struct, kw_only=True):
    """Response returned after voting on a comment."""

    comment_id: str
    upvotes_count: int
    downvotes_count: int
    popularity_score: int
    user_vote: int | None

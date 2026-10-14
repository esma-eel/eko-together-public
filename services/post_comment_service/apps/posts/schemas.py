"""Typed DTO Schemas for Post Service.

Built using high-performance msgspec.Struct for instantaneous validation
and serialization. No Django ORM models - all persistence is via MongoDB.
"""

from __future__ import annotations

import msgspec

# ============================================================================
# Path & Query Schemas
# ============================================================================


class PostIdPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for post ID resolution."""

    post_id: str


class PostListQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for listing and filtering posts."""

    forum_id: str | None = None
    author_profile_id: str | None = None
    tag: str | None = None
    ordering: str = "-created_at"  # -created_at | -popularity_score | pin_order
    cursor: str | None = None
    page: int = 1
    page_size: int = 20


# ============================================================================
# Request Body Schemas
# ============================================================================


class PostCreateSchema(msgspec.Struct, kw_only=True):
    """Payload for creating a new post (profile post or forum post)."""

    title: str
    body: str
    forum_id: str | None = None
    image: str | None = None
    tags: list[str] = msgspec.field(default_factory=list)
    visibility: str = "PUBLIC"  # PUBLIC | FOLLOWERS_ONLY | PRIVATE
    comment_permission: str = "ANYONE"  # ANYONE | FOLLOWERS_ONLY | NO_ONE


class PostUpdateSchema(msgspec.Struct, kw_only=True):
    """Payload for partial update of a post (PATCH semantics)."""

    title: str | None = None
    body: str | None = None
    image: str | None = None
    tags: list[str] | None = None
    visibility: str | None = None
    comment_permission: str | None = None
    admin_visibility: str | None = None  # Forum admin/owner only: ALL | ADMINS_ONLY


class ArchivePostSchema(msgspec.Struct, kw_only=True):
    """Payload for toggling post archive state."""

    is_archived: bool


class PinPostSchema(msgspec.Struct, kw_only=True):
    """Payload for pinning or unpinning a post in a forum."""

    is_pinned: bool = True
    pin_order: int = 1


# ============================================================================
# Response Schemas
# ============================================================================


class TagSchema(msgspec.Struct, kw_only=True):
    """Inline tag representation embedded in post responses."""

    name: str
    slug: str


class PostResponseSchema(msgspec.Struct, kw_only=True):
    """Full serialized representation of a post document."""

    id: str
    author_profile_id: str
    forum_id: str | None
    title: str
    body: str
    image: str | None
    tags: list[TagSchema]
    visibility: str
    comment_permission: str
    admin_visibility: str
    is_pinned: bool
    pin_order: int
    is_archived: bool
    is_deleted: bool
    upvotes_count: int
    downvotes_count: int
    popularity_score: int
    comments_count: int
    created_at: str
    updated_at: str


class PostListResponseSchema(msgspec.Struct, kw_only=True):
    """Paginated list of post documents."""

    count: int
    next_cursor: str | None
    results: list[PostResponseSchema]


class PostArchiveResponseSchema(msgspec.Struct, kw_only=True):
    """Minimal response returned after archiving a post."""

    id: str
    is_archived: bool
    updated_at: str


class PostPinResponseSchema(msgspec.Struct, kw_only=True):
    """Minimal response returned after pinning/unpinning a post."""

    id: str
    is_pinned: bool
    pin_order: int
    updated_at: str

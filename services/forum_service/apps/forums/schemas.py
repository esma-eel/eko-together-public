"""Typed DTO Schemas for Forum Service.

Built using high-performance msgspec.Struct for instantaneous validation and serialization.
"""

from __future__ import annotations

import msgspec


class ForumSlugPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for slug-based forum resolution."""

    slug: str


class ForumFilterQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for listing and searching forums."""

    search: str | None = None
    page: int = 1
    page_size: int = 20


class ForumCreateSchema(msgspec.Struct, kw_only=True):
    """Payload for creating a new sub-community forum."""

    title: str
    slug: str
    description: str = ""
    rules: str = ""
    avatar: str | None = None
    cover_image: str | None = None
    require_approval_to_join: bool = False
    post_permission: str = "ALL_MEMBERS"
    is_comments_locked: bool = False


class ForumUpdateSchema(msgspec.Struct, kw_only=True):
    """Payload for partial update of forum settings and metadata."""

    title: str | None = None
    description: str | None = None
    rules: str | None = None
    avatar: str | None = None
    cover_image: str | None = None
    require_approval_to_join: bool | None = None
    post_permission: str | None = None
    is_comments_locked: bool | None = None


class ForumResponseSchema(msgspec.Struct, kw_only=True):
    """Standard serialized representation of a forum."""

    id: str
    title: str
    slug: str
    description: str
    rules: str
    avatar: str | None
    cover_image: str | None
    require_approval_to_join: bool
    post_permission: str
    is_comments_locked: bool
    owner_profile_id: str
    members_count: int
    created_at: str
    updated_at: str


class ForumDetailResponseSchema(msgspec.Struct, kw_only=True):
    """Forum representation enriched with requester's membership details."""

    id: str
    title: str
    slug: str
    description: str
    rules: str
    avatar: str | None
    cover_image: str | None
    require_approval_to_join: bool
    post_permission: str
    is_comments_locked: bool
    owner_profile_id: str
    members_count: int
    created_at: str
    updated_at: str
    is_member: bool = False
    my_role: str | None = None
    my_status: str | None = None


class ForumListResponseSchema(msgspec.Struct, kw_only=True):
    """Paginated list of forums."""

    count: int
    results: list[ForumResponseSchema]


class ForumMemberPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for targeting a specific member in a forum."""

    slug: str
    user_profile_id: str


class ForumMemberListQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for filtering forum members."""

    role: str | None = None
    status: str | None = None
    page: int = 1
    page_size: int = 20


class ForumMemberItemSchema(msgspec.Struct, kw_only=True):
    """Representation of an individual forum member entry."""

    id: int
    forum_id: str
    user_profile_id: str
    role: str
    status: str
    joined_at: str


class ForumMemberListResponseSchema(msgspec.Struct, kw_only=True):
    """Paginated list of forum members."""

    count: int
    results: list[ForumMemberItemSchema]


class JoinForumResponseSchema(msgspec.Struct, kw_only=True):
    """Response returned upon joining or applying to join a forum."""

    status: str
    message: str


class UpdateMemberRoleStatusSchema(msgspec.Struct, kw_only=True):
    """Payload for modifying a member's role or status."""

    role: str | None = None
    status: str | None = None


class ForumPostPinPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for pinning a post in a forum."""

    slug: str
    post_id: str


class PinPostRequestSchema(msgspec.Struct, kw_only=True):
    """Payload for pinning or unpinning a post."""

    is_pinned: bool = True
    pin_order: int = 1


class PinPostResponseSchema(msgspec.Struct, kw_only=True):
    """Response returned upon pinning/unpinning a post."""

    post_id: str
    forum_id: str
    is_pinned: bool
    pin_order: int
    active_pins_count: int


class PinnedPostItemSchema(msgspec.Struct, kw_only=True):
    """Record of a pinned post in a forum."""

    id: int
    post_id: str
    pin_order: int
    is_pinned: bool
    pinned_by_profile_id: str
    created_at: str


class PinnedPostListResponseSchema(msgspec.Struct, kw_only=True):
    """List of active pinned posts in a forum."""

    count: int
    results: list[PinnedPostItemSchema]


class InternalForumPathSchema(msgspec.Struct, kw_only=True):
    """Path parameter schema for internal forum lookup."""

    forum_id: str


class InternalPermissionQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for internal service posting permission verification."""

    user_profile_id: str
    admin_visibility: str = "ALL"


class CheckPostPermissionResponseSchema(msgspec.Struct, kw_only=True):
    """Response returned for internal permission queries."""

    can_post: bool
    forum_id: str
    post_permission: str
    is_comments_locked: bool
    user_role: str | None
    user_status: str | None
    reason: str | None

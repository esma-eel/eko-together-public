"""Forum domain events emitted by Forum Service."""

from __future__ import annotations

from uuid import UUID

from shared.events.base import BaseEvent


class ForumCreatedEvent(BaseEvent, kw_only=True):
    """Emitted when a new sub-community forum is created."""

    event_type: str = "forum.created"
    forum_id: UUID
    title: str
    slug: str
    owner_profile_id: UUID
    description: str = ""
    avatar: str | None = None
    cover_image: str | None = None
    require_approval_to_join: bool = False
    post_permission: str = "ALL_MEMBERS"
    owner_display_name: str | None = None


class ForumUpdatedEvent(BaseEvent, kw_only=True):
    """Emitted when forum settings, description, or rules are updated."""

    event_type: str = "forum.updated"
    forum_id: UUID
    title: str
    slug: str
    description: str = ""
    avatar: str | None = None
    cover_image: str | None = None
    is_comments_locked: bool = False
    post_permission: str = "ALL_MEMBERS"


class ForumDeletedEvent(BaseEvent, kw_only=True):
    """Emitted when a forum is deleted or archived."""

    event_type: str = "forum.deleted"
    forum_id: UUID
    slug: str


class ForumMemberJoinedEvent(BaseEvent, kw_only=True):
    """Emitted when a user joins or is approved into a forum."""

    event_type: str = "forum.member_joined"
    forum_id: UUID
    user_profile_id: UUID
    role: str = "MEMBER"


class ForumMemberLeftEvent(BaseEvent, kw_only=True):
    """Emitted when a user leaves or is removed from a forum."""

    event_type: str = "forum.member_left"
    forum_id: UUID
    user_profile_id: UUID

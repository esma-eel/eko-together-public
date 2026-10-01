"""Post and comment events emitted by Post & Comment Service."""

from __future__ import annotations

from uuid import UUID

import msgspec

from shared.events.base import BaseEvent


class PostCreatedEvent(BaseEvent, kw_only=True):
    """Emitted when a new post document is inserted into MongoDB."""

    event_type: str = "post.created"
    post_id: UUID
    author_profile_id: UUID
    forum_id: UUID | None
    title: str
    tags: list[str] = msgspec.field(default_factory=list)
    image_url: str | None = None
    body: str = ""
    visibility: str = "PUBLIC"
    author_display_name: str | None = None
    forum_title: str | None = None
    forum_slug: str | None = None


class PostUpdatedEvent(BaseEvent, kw_only=True):
    """Emitted when a post document is updated."""

    event_type: str = "post.updated"
    post_id: UUID
    author_profile_id: UUID
    forum_id: UUID | None
    title: str
    tags: list[str] = msgspec.field(default_factory=list)
    image_url: str | None = None
    body: str = ""
    visibility: str = "PUBLIC"
    author_display_name: str | None = None
    forum_title: str | None = None
    forum_slug: str | None = None


class PostDeletedEvent(BaseEvent, kw_only=True):
    """Emitted when a post is soft or hard deleted."""

    event_type: str = "post.deleted"
    post_id: UUID
    author_profile_id: UUID
    forum_id: UUID | None


class CommentCreatedEvent(BaseEvent, kw_only=True):
    """Emitted when a comment or nested reply is added."""

    event_type: str = "comment.created"
    comment_id: UUID
    post_id: UUID
    user_profile_id: UUID
    parent_id: UUID | None
    depth: int
    body: str = ""
    post_title: str | None = None
    author_display_name: str | None = None
    forum_id: UUID | None = None


class CommentUpdatedEvent(BaseEvent, kw_only=True):
    """Emitted when comment content is updated."""

    event_type: str = "comment.updated"
    comment_id: UUID
    post_id: UUID
    user_profile_id: UUID
    body: str = ""


class CommentDeletedEvent(BaseEvent, kw_only=True):
    """Emitted when a comment is marked as deleted."""

    event_type: str = "comment.deleted"
    comment_id: UUID
    post_id: UUID

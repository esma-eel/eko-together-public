"""Unit tests for msgspec event schemas and serialization."""

from __future__ import annotations

from uuid import uuid4

from shared.events.base import deserialize_event, serialize_event
from shared.events.constants import (
    ROUTING_COMMENT_CREATED,
    ROUTING_COMMENT_DELETED,
    ROUTING_COMMENT_UPDATED,
    ROUTING_FORUM_CREATED,
    ROUTING_FORUM_DELETED,
    ROUTING_FORUM_MEMBER_JOINED,
    ROUTING_FORUM_MEMBER_LEFT,
    ROUTING_FORUM_UPDATED,
    ROUTING_POST_CREATED,
    ROUTING_POST_DELETED,
    ROUTING_POST_UPDATED,
    ROUTING_PROFILE_UPDATED,
    ROUTING_USER_REGISTERED,
    ROUTING_VOTE_CAST,
    ROUTING_VOTE_REVOKED,
)
from shared.events.forums import (
    ForumCreatedEvent,
    ForumDeletedEvent,
    ForumMemberJoinedEvent,
    ForumMemberLeftEvent,
    ForumUpdatedEvent,
)
from shared.events.posts import (
    CommentCreatedEvent,
    CommentDeletedEvent,
    CommentUpdatedEvent,
    PostCreatedEvent,
    PostDeletedEvent,
    PostUpdatedEvent,
)
from shared.events.users import UserProfileUpdatedEvent, UserRegisteredEvent
from shared.events.voting import VoteCastEvent, VoteRevokedEvent


def test_vote_cast_event_serialization_roundtrip() -> None:
    target_id = uuid4()
    profile_id = uuid4()

    event = VoteCastEvent(
        target_type="POST",
        target_id=target_id,
        user_profile_id=profile_id,
        delta_up=1,
        delta_down=0,
        net_delta=1,
    )

    encoded = serialize_event(event)
    assert isinstance(encoded, bytes)

    decoded = deserialize_event(encoded, VoteCastEvent)
    assert decoded.event_type == "vote.cast"
    assert decoded.target_type == "POST"
    assert decoded.target_id == target_id
    assert decoded.user_profile_id == profile_id
    assert decoded.net_delta == 1


def test_vote_revoked_event() -> None:
    target_id = uuid4()
    profile_id = uuid4()

    event = VoteRevokedEvent(
        target_type="COMMENT",
        target_id=target_id,
        user_profile_id=profile_id,
        previous_value=-1,
    )

    encoded = serialize_event(event)
    decoded = deserialize_event(encoded, VoteRevokedEvent)
    assert decoded.event_type == "vote.revoked"
    assert decoded.previous_value == -1


def test_post_created_event_serialization() -> None:
    post_id = uuid4()
    author_id = uuid4()
    forum_id = uuid4()

    event = PostCreatedEvent(
        post_id=post_id,
        author_profile_id=author_id,
        forum_id=forum_id,
        title="Django & NoSQL Architecture",
        tags=["django", "nosql", "architecture"],
        image_url="https://s3.example.com/image.png",
    )

    encoded = serialize_event(event)
    decoded = deserialize_event(encoded, PostCreatedEvent)
    assert decoded.post_id == post_id
    assert decoded.tags == ["django", "nosql", "architecture"]
    assert decoded.image_url == "https://s3.example.com/image.png"

    deleted_event = PostDeletedEvent(
        post_id=post_id,
        author_profile_id=author_id,
        forum_id=forum_id,
    )
    decoded_deleted = deserialize_event(serialize_event(deleted_event), PostDeletedEvent)
    assert decoded_deleted.event_type == "post.deleted"
    assert decoded_deleted.post_id == post_id


def test_comment_created_event_serialization() -> None:
    comment_id = uuid4()
    post_id = uuid4()
    user_id = uuid4()
    parent_id = uuid4()

    event = CommentCreatedEvent(
        comment_id=comment_id,
        post_id=post_id,
        user_profile_id=user_id,
        parent_id=parent_id,
        depth=2,
    )

    encoded = serialize_event(event)
    decoded = deserialize_event(encoded, CommentCreatedEvent)
    assert decoded.depth == 2
    assert decoded.parent_id == parent_id

    comment_deleted = CommentDeletedEvent(
        comment_id=comment_id,
        post_id=post_id,
    )
    decoded_comment_deleted = deserialize_event(
        serialize_event(comment_deleted),
        CommentDeletedEvent,
    )
    assert decoded_comment_deleted.event_type == "comment.deleted"
    assert decoded_comment_deleted.comment_id == comment_id


def test_forum_events() -> None:
    forum_id = uuid4()
    owner_id = uuid4()

    created_event = ForumCreatedEvent(
        forum_id=forum_id,
        title="Technology & Software",
        slug="technology-software",
        owner_profile_id=owner_id,
    )
    encoded = serialize_event(created_event)
    decoded_created = deserialize_event(encoded, ForumCreatedEvent)
    assert decoded_created.slug == "technology-software"

    updated_event = ForumUpdatedEvent(
        forum_id=forum_id,
        title="Technology & Modern Software",
        slug="technology-modern-software",
        is_comments_locked=True,
    )
    decoded_updated = deserialize_event(serialize_event(updated_event), ForumUpdatedEvent)
    assert decoded_updated.is_comments_locked is True

    member_event = ForumMemberJoinedEvent(
        forum_id=forum_id,
        user_profile_id=owner_id,
        role="ADMIN",
    )
    decoded_member = deserialize_event(serialize_event(member_event), ForumMemberJoinedEvent)
    assert decoded_member.role == "ADMIN"

    left_event = ForumMemberLeftEvent(
        forum_id=forum_id,
        user_profile_id=owner_id,
    )
    decoded_left = deserialize_event(serialize_event(left_event), ForumMemberLeftEvent)
    assert decoded_left.event_type == "forum.member_left"
    assert decoded_left.forum_id == forum_id

    deleted_event = ForumDeletedEvent(
        forum_id=forum_id,
        slug="technology-software",
    )
    decoded_deleted = deserialize_event(serialize_event(deleted_event), ForumDeletedEvent)
    assert decoded_deleted.event_type == "forum.deleted"
    assert decoded_deleted.slug == "technology-software"


def test_post_and_comment_updated_events() -> None:
    post_id = uuid4()
    author_id = uuid4()
    forum_id = uuid4()

    post_updated = PostUpdatedEvent(
        post_id=post_id,
        author_profile_id=author_id,
        forum_id=forum_id,
        title="Updated Title",
        tags=["python", "fast"],
    )
    decoded_post = deserialize_event(serialize_event(post_updated), PostUpdatedEvent)
    assert decoded_post.event_type == "post.updated"
    assert decoded_post.title == "Updated Title"

    comment_id = uuid4()
    comment_updated = CommentUpdatedEvent(
        comment_id=comment_id,
        post_id=post_id,
        user_profile_id=author_id,
    )
    decoded_comment = deserialize_event(serialize_event(comment_updated), CommentUpdatedEvent)
    assert decoded_comment.event_type == "comment.updated"
    assert decoded_comment.comment_id == comment_id


def test_user_events() -> None:
    user_id = uuid4()
    profile_id = uuid4()

    reg_event = UserRegisteredEvent(
        user_id=user_id,
        profile_id=profile_id,
        username="johndoe",
        email="john@example.com",
    )
    decoded_reg = deserialize_event(serialize_event(reg_event), UserRegisteredEvent)
    assert decoded_reg.event_type == "user.registered"
    assert decoded_reg.username == "johndoe"

    event = UserProfileUpdatedEvent(
        user_id=user_id,
        profile_id=profile_id,
        display_name="Software Engineer",
        avatar="https://s3.example.com/avatar.jpg",
        is_private=True,
    )

    encoded = serialize_event(event)
    decoded = deserialize_event(encoded, UserProfileUpdatedEvent)
    assert decoded.display_name == "Software Engineer"
    assert decoded.is_private is True


def test_routing_keys_match_events() -> None:
    assert ROUTING_VOTE_CAST == "vote.cast"
    assert ROUTING_VOTE_REVOKED == "vote.revoked"
    assert ROUTING_POST_CREATED == "post.created"
    assert ROUTING_POST_UPDATED == "post.updated"
    assert ROUTING_POST_DELETED == "post.deleted"
    assert ROUTING_COMMENT_CREATED == "comment.created"
    assert ROUTING_COMMENT_UPDATED == "comment.updated"
    assert ROUTING_COMMENT_DELETED == "comment.deleted"
    assert ROUTING_FORUM_CREATED == "forum.created"
    assert ROUTING_FORUM_UPDATED == "forum.updated"
    assert ROUTING_FORUM_DELETED == "forum.deleted"
    assert ROUTING_FORUM_MEMBER_JOINED == "forum.member_joined"
    assert ROUTING_FORUM_MEMBER_LEFT == "forum.member_left"
    assert ROUTING_USER_REGISTERED == "user.registered"
    assert ROUTING_PROFILE_UPDATED == "profile.updated"

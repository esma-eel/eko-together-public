"""Tests for RabbitMQ event ingestion worker and search management commands."""

from __future__ import annotations

import uuid
from io import StringIO

from django.core.management import call_command

from services.search_service.apps.search.indices import (
    INDEX_COMMENTS,
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
)
from services.search_service.workers.search_consumer import process_search_event_message
from shared.events import (
    CommentCreatedEvent,
    CommentDeletedEvent,
    CommentUpdatedEvent,
    ForumCreatedEvent,
    ForumDeletedEvent,
    ForumUpdatedEvent,
    PostCreatedEvent,
    PostDeletedEvent,
    PostUpdatedEvent,
    UserProfileUpdatedEvent,
    VoteCastEvent,
    VoteRevokedEvent,
    serialize_event,
)
from tests.test_search_service.conftest import MockElasticsearch


def test_process_post_lifecycle_events(mock_es: MockElasticsearch) -> None:
    """Post created, updated, and deleted events correctly sync to posts_index."""
    post_id = uuid.uuid4()
    author_id = uuid.uuid4()
    forum_id = uuid.uuid4()

    # 1. Post Created
    create_evt = PostCreatedEvent(
        post_id=post_id,
        author_profile_id=author_id,
        forum_id=forum_id,
        title="Event Driven Search",
        body="Indexing full text documents asynchronously",
        tags=["es", "events"],
        image_url="https://cdn.example.com/es.png",
        visibility="PUBLIC",
    )
    success = process_search_event_message(serialize_event(create_evt), client=mock_es)
    assert success is True

    doc = mock_es.data[INDEX_POSTS][str(post_id)]
    assert doc["title"] == "Event Driven Search"
    assert doc["body"] == "Indexing full text documents asynchronously"
    assert doc["tags"] == ["es", "events"]
    assert doc["has_image"] is True
    assert doc["is_deleted"] is False

    # 2. Post Updated
    update_evt = PostUpdatedEvent(
        post_id=post_id,
        author_profile_id=author_id,
        forum_id=forum_id,
        title="Event Driven Search (Updated)",
        body="Updated text body",
        tags=["es", "events", "v2"],
    )
    success = process_search_event_message(serialize_event(update_evt), client=mock_es)
    assert success is True

    updated_doc = mock_es.data[INDEX_POSTS][str(post_id)]
    assert updated_doc["title"] == "Event Driven Search (Updated)"
    assert updated_doc["body"] == "Updated text body"
    assert updated_doc["tags"] == ["es", "events", "v2"]

    # 3. Post Deleted
    delete_evt = PostDeletedEvent(
        post_id=post_id,
        author_profile_id=author_id,
        forum_id=forum_id,
    )
    success = process_search_event_message(serialize_event(delete_evt), client=mock_es)
    assert success is True

    deleted_doc = mock_es.data[INDEX_POSTS][str(post_id)]
    assert deleted_doc["is_deleted"] is True


def test_process_comment_lifecycle_events(mock_es: MockElasticsearch) -> None:
    """Comment created, updated, and deleted events sync to comments_index."""
    comm_id = uuid.uuid4()
    post_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # 1. Created
    c_evt = CommentCreatedEvent(
        comment_id=comm_id,
        post_id=post_id,
        user_profile_id=user_id,
        parent_id=None,
        depth=0,
        body="Initial thoughtful comment",
        post_title="Original Post",
    )
    success = process_search_event_message(serialize_event(c_evt), client=mock_es)
    assert success is True

    cdoc = mock_es.data[INDEX_COMMENTS][str(comm_id)]
    assert cdoc["body"] == "Initial thoughtful comment"
    assert cdoc["is_deleted"] is False

    # 2. Updated
    cu_evt = CommentUpdatedEvent(
        comment_id=comm_id,
        post_id=post_id,
        user_profile_id=user_id,
        body="Revised thoughtful comment",
    )
    success = process_search_event_message(serialize_event(cu_evt), client=mock_es)
    assert success is True
    assert mock_es.data[INDEX_COMMENTS][str(comm_id)]["body"] == "Revised thoughtful comment"

    # 3. Deleted
    cd_evt = CommentDeletedEvent(comment_id=comm_id, post_id=post_id)
    success = process_search_event_message(serialize_event(cd_evt), client=mock_es)
    assert success is True
    assert mock_es.data[INDEX_COMMENTS][str(comm_id)]["is_deleted"] is True


def test_process_forum_lifecycle_events(mock_es: MockElasticsearch) -> None:
    """Forum created, updated, and deleted events sync to forums_index."""
    forum_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    # Created
    f_create = ForumCreatedEvent(
        forum_id=forum_id,
        title="Microservices Community",
        slug="microservices",
        owner_profile_id=owner_id,
        description="Architecture discussions",
    )
    success = process_search_event_message(serialize_event(f_create), client=mock_es)
    assert success is True
    assert str(forum_id) in mock_es.data[INDEX_FORUMS]

    # Updated
    f_update = ForumUpdatedEvent(
        forum_id=forum_id,
        title="Microservices & Distributed Systems",
        slug="microservices",
        description="Updated architecture discussions",
        is_comments_locked=True,
    )
    success = process_search_event_message(serialize_event(f_update), client=mock_es)
    assert success is True
    assert (
        mock_es.data[INDEX_FORUMS][str(forum_id)]["title"] == "Microservices & Distributed Systems"
    )
    assert mock_es.data[INDEX_FORUMS][str(forum_id)]["is_comments_locked"] is True

    # Deleted
    f_delete = ForumDeletedEvent(forum_id=forum_id, slug="microservices")
    success = process_search_event_message(serialize_event(f_delete), client=mock_es)
    assert success is True
    assert str(forum_id) not in mock_es.data[INDEX_FORUMS]


def test_process_profile_updated_event(mock_es: MockElasticsearch) -> None:
    """UserProfileUpdatedEvent upserts document into profiles_index."""
    user_id = uuid.uuid4()
    prof_id = uuid.uuid4()

    p_evt = UserProfileUpdatedEvent(
        user_id=user_id,
        profile_id=prof_id,
        username="lead_architect",
        display_name="Lead Architect",
        bio="Designing large scale architectures",
        is_private=False,
    )
    success = process_search_event_message(serialize_event(p_evt), client=mock_es)
    assert success is True

    doc = mock_es.data[INDEX_PROFILES][str(prof_id)]
    assert doc["username"] == "lead_architect"
    assert doc["bio"] == "Designing large scale architectures"


def test_process_vote_cast_and_revoked(mock_es: MockElasticsearch) -> None:
    """VoteCastEvent and VoteRevokedEvent atomically update popularity_score."""
    post_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # Seed post
    mock_es.index(
        index=INDEX_POSTS,
        id=str(post_id),
        document={
            "id": str(post_id),
            "title": "Voted Post",
            "upvotes_count": 0,
            "downvotes_count": 0,
            "popularity_score": 0,
        },
    )

    # Cast Upvote
    cast_evt = VoteCastEvent(
        user_profile_id=user_id,
        target_type="POST",
        target_id=post_id,
        delta_up=1,
        delta_down=0,
        net_delta=1,
    )
    success = process_search_event_message(serialize_event(cast_evt), client=mock_es)
    assert success is True
    doc = mock_es.data[INDEX_POSTS][str(post_id)]
    assert doc["upvotes_count"] == 1
    assert doc["popularity_score"] == 1

    # Revoke Vote
    revoke_evt = VoteRevokedEvent(
        user_profile_id=user_id,
        target_type="POST",
        target_id=post_id,
        previous_value=1,
    )
    success = process_search_event_message(serialize_event(revoke_evt), client=mock_es)
    assert success is True
    doc = mock_es.data[INDEX_POSTS][str(post_id)]
    assert doc["upvotes_count"] == 0
    assert doc["popularity_score"] == 0


def test_setup_search_indices_command(mock_es: MockElasticsearch) -> None:
    """setup_search_indices Django management command executes successfully."""
    out = StringIO()
    call_command("setup_search_indices", "--recreate", stdout=out)
    output = out.getvalue()

    assert "Setting up Elasticsearch indices" in output
    assert "posts_index" in output
    assert "forums_index" in output
    assert "profiles_index" in output
    assert "comments_index" in output
    assert "Elasticsearch indices setup completed successfully" in output

"""Tests for Forums, Comments, and Media search endpoints."""

from __future__ import annotations

import uuid

from dmr.test import DMRClient

from services.search_service.apps.search.indices import (
    INDEX_COMMENTS,
    INDEX_FORUMS,
    INDEX_POSTS,
)
from tests.test_search_service.conftest import MockElasticsearch

# ============================================================================
# Forums Search Tests
# ============================================================================


def test_forums_search_keywords_and_filters(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Forums search matches query and respects post_permission filter."""
    f1 = str(uuid.uuid4())
    f2 = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_FORUMS,
        id=f1,
        document={
            "id": f1,
            "title": "Django Advanced Community",
            "slug": "django-advanced",
            "description": "Deep dive into Django internals",
            "post_permission": "APPROVED_ONLY",
            "is_comments_locked": False,
            "members_count": 1500,
            "created_at": "2026-01-01T10:00:00Z",
        },
    )
    mock_es.index(
        index=INDEX_FORUMS,
        id=f2,
        document={
            "id": f2,
            "title": "Django Beginners Group",
            "slug": "django-beginners",
            "description": "Welcome to Django world",
            "post_permission": "ALL_MEMBERS",
            "is_comments_locked": False,
            "members_count": 500,
            "created_at": "2026-02-01T10:00:00Z",
        },
    )

    # Search with post_permission filter
    resp = dmr_client.get("/api/v1/search/forums/?q=Django&post_permission=APPROVED_ONLY")
    assert resp.status_code == 200
    data = resp.json()

    assert data["meta"]["total_count"] == 1
    assert data["results"][0]["id"] == f1
    assert data["results"][0]["slug"] == "django-advanced"
    assert data["results"][0]["members_count"] == 1500


def test_forums_search_sorting(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Forums search sorts by members_count descending."""
    f1 = str(uuid.uuid4())
    f2 = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_FORUMS,
        id=f1,
        document={
            "id": f1,
            "title": "Python Devs",
            "slug": "python-devs",
            "description": "Python developers community",
            "members_count": 200,
            "created_at": "2026-01-01T10:00:00Z",
        },
    )
    mock_es.index(
        index=INDEX_FORUMS,
        id=f2,
        document={
            "id": f2,
            "title": "Python Masters",
            "slug": "python-masters",
            "description": "Python masters community",
            "members_count": 8000,
            "created_at": "2026-02-01T10:00:00Z",
        },
    )

    resp = dmr_client.get("/api/v1/search/forums/?q=Python&sort_by=members_count")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["results"]) == 2
    assert data["results"][0]["id"] == f2
    assert data["results"][0]["members_count"] == 8000


# ============================================================================
# Comments Search Tests
# ============================================================================


def test_comments_search_post_filter_and_highlight(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Comments search returns highlights and filters by post_id."""
    post_id = str(uuid.uuid4())
    other_post_id = str(uuid.uuid4())
    c1 = str(uuid.uuid4())
    c2 = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_COMMENTS,
        id=c1,
        document={
            "id": c1,
            "post_id": post_id,
            "post_title": "Scalable Microservices",
            "body": "We should use asynchronous event-driven messaging",
            "author_id": str(uuid.uuid4()),
            "author_display_name": "Senior Arch",
            "depth": 1,
            "popularity_score": 25,
            "is_deleted": False,
            "created_at": "2026-08-16T12:00:00Z",
        },
    )
    mock_es.index(
        index=INDEX_COMMENTS,
        id=c2,
        document={
            "id": c2,
            "post_id": other_post_id,
            "post_title": "Other Topic",
            "body": "Another comment about event-driven design",
            "author_id": str(uuid.uuid4()),
            "depth": 0,
            "popularity_score": 5,
            "is_deleted": False,
            "created_at": "2026-08-16T13:00:00Z",
        },
    )

    resp = dmr_client.get(f"/api/v1/search/comments/?q=event-driven&post_id={post_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["meta"]["total_count"] == 1
    assert data["results"][0]["id"] == c1
    assert data["results"][0]["post_id"] == post_id
    assert "<b>event-driven</b>" in data["results"][0]["snippet"].lower()


# ============================================================================
# Media Search Tests
# ============================================================================


def test_media_search_queries_post_images(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Media search retrieves image attachments from public posts."""
    pid = str(uuid.uuid4())
    author_id = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_POSTS,
        id=pid,
        document={
            "id": pid,
            "title": "System Architecture Blueprint",
            "body": "Comprehensive diagram of cloud services",
            "image": "https://cdn.example.com/posts/system_diagram.png",
            "has_image": True,
            "forum_slug": "architecture-hub",
            "author_id": author_id,
            "author_display_name": "Dev Expert",
            "is_deleted": False,
            "visibility": "PUBLIC",
            "popularity_score": 90,
            "created_at": "2026-08-15T10:30:00Z",
        },
    )

    resp = dmr_client.get("/api/v1/search/media/?q=Architecture")
    assert resp.status_code == 200
    data = resp.json()

    assert data["meta"]["total_count"] == 1
    media_item = data["results"][0]
    assert media_item["media_url"] == "https://cdn.example.com/posts/system_diagram.png"
    assert media_item["post"]["id"] == pid
    assert media_item["post"]["forum_slug"] == "architecture-hub"
    assert media_item["author"]["id"] == author_id

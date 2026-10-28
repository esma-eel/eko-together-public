"""Tests for GET /api/v1/search/posts/ (Dedicated Post Search)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from dmr.test import DMRClient

from services.search_service.apps.search.indices import INDEX_POSTS
from tests.test_search_service.conftest import MockElasticsearch


def test_posts_search_keywords_and_highlight(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Posts search matches keywords and returns highlight snippets."""
    post_id = str(uuid.uuid4())
    mock_es.index(
        index=INDEX_POSTS,
        id=post_id,
        document={
            "id": post_id,
            "title": "Scaling Distributed Systems with Event Architecture",
            "body": "Detailed discussion on event-driven architecture and asynchronous messaging",
            "tags": ["architecture", "events"],
            "author_id": str(uuid.uuid4()),
            "author_display_name": "Dev Expert",
            "is_deleted": False,
            "visibility": "PUBLIC",
            "popularity_score": 100,
            "created_at": "2026-08-15T10:00:00Z",
        },
    )

    resp = dmr_client.get("/api/v1/search/posts/?q=event-driven")
    assert resp.status_code == 200
    data = resp.json()

    assert data["meta"]["total_count"] == 1
    post = data["results"][0]
    assert post["id"] == post_id
    assert "<b>event-driven</b>" in post["snippet"].lower()


def test_posts_search_tags_filter(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Posts search correctly filters by tags list."""
    p1 = str(uuid.uuid4())
    p2 = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_POSTS,
        id=p1,
        document={
            "id": p1,
            "title": "Post about Python and Django",
            "body": "Python content",
            "tags": ["python", "django"],
            "author_id": str(uuid.uuid4()),
            "is_deleted": False,
            "visibility": "PUBLIC",
            "created_at": "2026-08-15T10:00:00Z",
        },
    )
    mock_es.index(
        index=INDEX_POSTS,
        id=p2,
        document={
            "id": p2,
            "title": "Post about Go and Kubernetes",
            "body": "Golang content",
            "tags": ["golang", "kubernetes"],
            "author_id": str(uuid.uuid4()),
            "is_deleted": False,
            "visibility": "PUBLIC",
            "created_at": "2026-08-15T10:00:00Z",
        },
    )

    resp = dmr_client.get("/api/v1/search/posts/?tags=django")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total_count"] == 1
    assert data["results"][0]["id"] == p1


def test_posts_search_has_image_and_forum_filter(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Posts search filters by has_image and forum_id."""
    target_forum = str(uuid.uuid4())
    p_img = str(uuid.uuid4())
    p_no_img = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_POSTS,
        id=p_img,
        document={
            "id": p_img,
            "title": "Diagram Post",
            "body": "Look at the diagram",
            "image": "https://cdn.example.com/diag.png",
            "has_image": True,
            "forum_id": target_forum,
            "author_id": str(uuid.uuid4()),
            "is_deleted": False,
            "visibility": "PUBLIC",
            "created_at": "2026-08-15T10:00:00Z",
        },
    )
    mock_es.index(
        index=INDEX_POSTS,
        id=p_no_img,
        document={
            "id": p_no_img,
            "title": "Text Post",
            "body": "No image here",
            "has_image": False,
            "forum_id": target_forum,
            "author_id": str(uuid.uuid4()),
            "is_deleted": False,
            "visibility": "PUBLIC",
            "created_at": "2026-08-15T10:00:00Z",
        },
    )

    resp = dmr_client.get(f"/api/v1/search/posts/?forum_id={target_forum}&has_image=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total_count"] == 1
    assert data["results"][0]["id"] == p_img


def test_posts_search_timeframe_filter(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """timeframe=day filters out posts older than 24 hours."""
    now = datetime.now(tz=UTC)
    recent_id = str(uuid.uuid4())
    old_id = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_POSTS,
        id=recent_id,
        document={
            "id": recent_id,
            "title": "Fresh Breaking News",
            "body": "Happened today",
            "author_id": str(uuid.uuid4()),
            "is_deleted": False,
            "visibility": "PUBLIC",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
    )
    mock_es.index(
        index=INDEX_POSTS,
        id=old_id,
        document={
            "id": old_id,
            "title": "Old News Archive",
            "body": "Happened last week",
            "author_id": str(uuid.uuid4()),
            "is_deleted": False,
            "visibility": "PUBLIC",
            "created_at": (now - timedelta(days=5)).isoformat(),
        },
    )

    resp = dmr_client.get("/api/v1/search/posts/?timeframe=day")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total_count"] == 1
    assert data["results"][0]["id"] == recent_id


def test_posts_search_sort_top_and_pagination(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """sort_by=top orders by popularity_score descending with pagination."""
    for i in range(5):
        pid = f"post-{i}"
        mock_es.index(
            index=INDEX_POSTS,
            id=pid,
            document={
                "id": pid,
                "title": f"Post Number {i}",
                "body": "Standard content body",
                "author_id": str(uuid.uuid4()),
                "is_deleted": False,
                "visibility": "PUBLIC",
                "popularity_score": i * 50,  # 0, 50, 100, 150, 200
                "created_at": f"2026-08-1{i}T10:00:00Z",
            },
        )

    # Page 1, size 2, sorted by top
    resp = dmr_client.get("/api/v1/search/posts/?sort_by=top&page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()

    assert data["meta"]["total_count"] == 5
    assert data["meta"]["total_pages"] == 3
    assert len(data["results"]) == 2
    assert data["results"][0]["id"] == "post-4"
    assert data["results"][0]["popularity_score"] == 200
    assert data["results"][1]["id"] == "post-3"
    assert data["results"][1]["popularity_score"] == 150


def test_posts_search_excludes_deleted(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Deleted posts (is_deleted=True) are excluded from search."""
    pid = str(uuid.uuid4())
    mock_es.index(
        index=INDEX_POSTS,
        id=pid,
        document={
            "id": pid,
            "title": "Deleted Post Sample",
            "body": "This was removed",
            "author_id": str(uuid.uuid4()),
            "is_deleted": True,
            "visibility": "PUBLIC",
            "created_at": "2026-08-15T10:00:00Z",
        },
    )

    resp = dmr_client.get("/api/v1/search/posts/?q=Deleted")
    assert resp.status_code == 200
    assert resp.json()["meta"]["total_count"] == 0

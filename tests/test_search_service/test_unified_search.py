"""Tests for GET /api/v1/search/ (Unified Multi-Entity Search)."""

from __future__ import annotations

import uuid

from dmr.test import DMRClient

from services.search_service.apps.search.indices import (
    INDEX_COMMENTS,
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
)
from tests.test_search_service.conftest import MockElasticsearch


def test_unified_search_returns_grouped_results(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """Unified search returns grouped results across all entity categories."""
    p_id = str(uuid.uuid4())
    f_id = str(uuid.uuid4())
    post_id = str(uuid.uuid4())
    comm_id = str(uuid.uuid4())

    # Seed profile
    mock_es.index(
        index=INDEX_PROFILES,
        id=p_id,
        document={
            "id": p_id,
            "username": "backend_dev",
            "display_name": "Dev Expert",
            "bio": "Django and distributed systems enthusiast",
            "avatar": "https://cdn.example.com/user.jpg",
            "is_private": False,
        },
    )

    # Seed forum
    mock_es.index(
        index=INDEX_FORUMS,
        id=f_id,
        document={
            "id": f_id,
            "title": "Django & Microservices",
            "slug": "django-microservices",
            "description": "Discussions on decoupling Django apps",
            "avatar": "https://cdn.example.com/django.jpg",
        },
    )

    # Seed post with image
    mock_es.index(
        index=INDEX_POSTS,
        id=post_id,
        document={
            "id": post_id,
            "title": "Scaling Django Services with CQRS",
            "body": "Detailed guide on django architecture and fast search",
            "image": "https://cdn.example.com/posts/cover.jpg",
            "has_image": True,
            "tags": ["django", "architecture"],
            "forum_id": f_id,
            "forum_title": "Django & Microservices",
            "forum_slug": "django-microservices",
            "author_id": p_id,
            "author_display_name": "Dev Expert",
            "is_deleted": False,
            "visibility": "PUBLIC",
            "popularity_score": 142,
            "created_at": "2026-08-15T10:30:00Z",
        },
    )

    # Seed comment
    mock_es.index(
        index=INDEX_COMMENTS,
        id=comm_id,
        document={
            "id": comm_id,
            "post_id": post_id,
            "post_title": "Scaling Django Services with CQRS",
            "body": "Check out django architecture patterns",
            "author_id": p_id,
            "author_display_name": "Dev Expert",
            "depth": 0,
            "popularity_score": 12,
            "is_deleted": False,
            "created_at": "2026-08-16T14:10:00Z",
        },
    )

    resp = dmr_client.get("/api/v1/search/?q=django")
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == "django"
    results = data["results"]
    assert len(results["profiles"]) == 1
    assert results["profiles"][0]["username"] == "backend_dev"

    assert len(results["forums"]) == 1
    assert results["forums"][0]["slug"] == "django-microservices"

    assert len(results["posts"]) == 1
    assert results["posts"][0]["id"] == post_id
    assert "<b>django</b>" in results["posts"][0]["snippet"].lower()

    assert len(results["comments"]) == 1
    assert results["comments"][0]["id"] == comm_id

    assert len(results["media"]) == 1
    assert results["media"][0]["media_url"] == "https://cdn.example.com/posts/cover.jpg"


def test_unified_search_types_filter(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """types parameter filters out unrequested entity categories."""
    p_id = str(uuid.uuid4())
    f_id = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_PROFILES,
        id=p_id,
        document={
            "id": p_id,
            "username": "python_coder",
            "display_name": "Python Coder",
            "is_private": False,
        },
    )
    mock_es.index(
        index=INDEX_FORUMS,
        id=f_id,
        document={
            "id": f_id,
            "title": "Python Experts",
            "slug": "python-experts",
        },
    )

    resp = dmr_client.get("/api/v1/search/?q=python&types=forums")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["results"]["forums"]) == 1
    assert len(data["results"]["profiles"]) == 0
    assert len(data["results"]["posts"]) == 0


def test_unified_search_privacy_filtering(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
    make_user_token,
) -> None:
    """Private profile is hidden for anonymous/other users, but returned for the owner."""
    owner_id = uuid.uuid4()
    mock_es.index(
        index=INDEX_PROFILES,
        id=str(owner_id),
        document={
            "id": str(owner_id),
            "username": "secret_agent",
            "display_name": "Classified User",
            "is_private": True,
        },
    )

    # Anonymous search
    anon_resp = dmr_client.get("/api/v1/search/?q=secret")
    assert anon_resp.status_code == 200
    assert len(anon_resp.json()["results"]["profiles"]) == 0

    # Other user search
    other_token, _, other_p_id = make_user_token(username="stranger")
    other_resp = dmr_client.get(
        "/api/v1/search/?q=secret",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_resp.status_code == 200
    assert len(other_resp.json()["results"]["profiles"]) == 0

    # Owner search
    owner_token, _, _ = make_user_token(profile_id=owner_id, username="secret_agent")
    owner_resp = dmr_client.get(
        "/api/v1/search/?q=secret",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_resp.status_code == 200
    profiles = owner_resp.json()["results"]["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["id"] == str(owner_id)
    assert profiles[0]["relation_status"] == "OWNER"

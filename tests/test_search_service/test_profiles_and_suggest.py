"""Tests for Profiles search and Suggest / Autocomplete endpoints."""

from __future__ import annotations

import uuid

from dmr.test import DMRClient

from services.search_service.apps.search.indices import (
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
)
from tests.test_search_service.conftest import MockElasticsearch


def test_profiles_search_public_and_private(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
    make_user_token,
) -> None:
    """Profiles search returns public profiles and hides private ones from unauthorized viewers."""
    public_id = str(uuid.uuid4())
    private_id = str(uuid.uuid4())

    mock_es.index(
        index=INDEX_PROFILES,
        id=public_id,
        document={
            "id": public_id,
            "username": "public_coder",
            "display_name": "Public Coder",
            "bio": "Coding in public",
            "is_private": False,
        },
    )
    mock_es.index(
        index=INDEX_PROFILES,
        id=private_id,
        document={
            "id": private_id,
            "username": "secret_coder",
            "display_name": "Secret Coder",
            "bio": "Private coder",
            "is_private": True,
        },
    )

    # Anonymous search for "coder"
    resp = dmr_client.get("/api/v1/search/profiles/?q=coder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["total_count"] == 1
    assert data["results"][0]["id"] == public_id

    # Owner search for private profile
    owner_token, _, _ = make_user_token(profile_id=uuid.UUID(private_id), username="secret_coder")
    owner_resp = dmr_client.get(
        "/api/v1/search/profiles/?q=coder",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_resp.status_code == 200
    owner_results = owner_resp.json()["results"]
    assert len(owner_results) == 2
    ids = {r["id"] for r in owner_results}
    assert public_id in ids
    assert private_id in ids


def test_suggest_autocomplete(
    dmr_client: DMRClient,
    mock_es: MockElasticsearch,
) -> None:
    """GET /api/v1/search/suggest/ returns prefix autocomplete suggestions."""
    f_id = str(uuid.uuid4())
    p_id = str(uuid.uuid4())
    post_id = str(uuid.uuid4())

    # Seed forum
    mock_es.index(
        index=INDEX_FORUMS,
        id=f_id,
        document={
            "id": f_id,
            "title": "Django & Microservices",
            "slug": "django-microservices",
        },
    )

    # Seed profile
    mock_es.index(
        index=INDEX_PROFILES,
        id=p_id,
        document={
            "id": p_id,
            "username": "django_ninja",
            "display_name": "Django Ninja",
            "is_private": False,
        },
    )

    # Seed post
    mock_es.index(
        index=INDEX_POSTS,
        id=post_id,
        document={
            "id": post_id,
            "title": "Django Architecture Best Practices",
            "is_deleted": False,
            "visibility": "PUBLIC",
        },
    )

    resp = dmr_client.get("/api/v1/search/suggest/?q=djan")
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) >= 1

    types = {s["type"] for s in suggestions}
    assert "forum" in types or "profile" in types or "post" in types


def test_suggest_short_query_returns_empty(
    dmr_client: DMRClient,
) -> None:
    """Autocomplete with fewer than 2 characters returns empty suggestions."""
    resp = dmr_client.get("/api/v1/search/suggest/?q=a")
    assert resp.status_code == 200
    assert resp.json()["suggestions"] == []

"""End-to-end HTTP integration tests for Voting Service endpoints."""

from __future__ import annotations

import json
import uuid
from http import HTTPStatus
from uuid import UUID

import pytest
from dmr.test import DMRClient


@pytest.mark.django_db
def test_post_vote_endpoint_flow(
    client: DMRClient,
    sample_post_id: UUID,
    voter_headers: dict[str, str],
):
    """Test full cycle of voting, flipping, and toggling via HTTP POST endpoint."""
    url = f"/api/v1/posts/{sample_post_id}/votes/"

    # 1. Cast Upvote
    resp = client.post(
        url,
        data=json.dumps({"value": 1}),
        content_type="application/json",
        **voter_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["target_id"] == str(sample_post_id)
    assert body["data"]["target_type"] == "POST"
    assert body["data"]["user_vote"] == 1
    assert body["data"]["upvotes_count"] == 1
    assert body["data"]["popularity_score"] == 1

    # 2. Check My Vote via GET
    me_url = f"/api/v1/posts/{sample_post_id}/votes/me/"
    resp_me = client.get(me_url, **voter_headers)
    assert resp_me.status_code == HTTPStatus.OK
    assert resp_me.json()["data"]["user_vote"] == 1

    # 3. Flip Vote to Downvote (-1)
    resp_flip = client.post(
        url,
        data=json.dumps({"value": -1}),
        content_type="application/json",
        **voter_headers,
    )
    assert resp_flip.status_code == HTTPStatus.OK
    body_flip = resp_flip.json()
    assert body_flip["data"]["user_vote"] == -1
    assert body_flip["data"]["upvotes_count"] == 0
    assert body_flip["data"]["downvotes_count"] == 1
    assert body_flip["data"]["popularity_score"] == -1

    # 4. Toggle Off (Clicking -1 again)
    resp_toggle = client.post(
        url,
        data=json.dumps({"value": -1}),
        content_type="application/json",
        **voter_headers,
    )
    assert resp_toggle.status_code == HTTPStatus.OK
    body_toggle = resp_toggle.json()
    assert body_toggle["data"]["user_vote"] is None
    assert body_toggle["data"]["downvotes_count"] == 0
    assert body_toggle["data"]["popularity_score"] == 0


@pytest.mark.django_db
def test_comment_vote_endpoint_flow(
    client: DMRClient,
    sample_comment_id: UUID,
    voter_headers: dict[str, str],
):
    """Test voting on comment entity via HTTP."""
    url = f"/api/v1/comments/{sample_comment_id}/votes/"

    resp = client.post(
        url,
        data=json.dumps({"value": 1}),
        content_type="application/json",
        **voter_headers,
    )
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert body["data"]["target_type"] == "COMMENT"
    assert body["data"]["user_vote"] == 1

    me_url = f"/api/v1/comments/{sample_comment_id}/votes/me/"
    resp_me = client.get(me_url, **voter_headers)
    assert resp_me.status_code == HTTPStatus.OK
    assert resp_me.json()["data"]["user_vote"] == 1


@pytest.mark.django_db
def test_voting_requires_authentication(
    client: DMRClient,
    sample_post_id: UUID,
):
    """Requests without Bearer token return 401 Unauthorized."""
    url = f"/api/v1/posts/{sample_post_id}/votes/"
    resp = client.post(
        url,
        data=json.dumps({"value": 1}),
        content_type="application/json",
    )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_voting_nonexistent_entity_returns_404(
    client: DMRClient,
    voter_headers: dict[str, str],
):
    """Voting on a missing post returns 404 Not Found."""
    fake_id = uuid.uuid4()
    url = f"/api/v1/posts/{fake_id}/votes/"
    resp = client.post(
        url,
        data=json.dumps({"value": 1}),
        content_type="application/json",
        **voter_headers,
    )
    assert resp.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_voting_rate_limiting_exceeded(
    client: DMRClient,
    sample_post_id: UUID,
    voter_headers: dict[str, str],
):
    """Burst rate limit of 20 requests per minute triggers 429 Too Many Requests."""
    url = f"/api/v1/posts/{sample_post_id}/votes/"

    # Make 20 requests
    for i in range(20):
        val = 1 if i % 2 == 0 else -1
        client.post(
            url,
            data=json.dumps({"value": val}),
            content_type="application/json",
            **voter_headers,
        )

    # 21st request exceeds burst rate
    resp_blocked = client.post(
        url,
        data=json.dumps({"value": 1}),
        content_type="application/json",
        **voter_headers,
    )
    assert resp_blocked.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert "Retry-After" in resp_blocked.headers or "retry-after" in resp_blocked.headers

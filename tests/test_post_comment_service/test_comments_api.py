"""Tests for Comments API, 3-tier depth limit, and tree-preserving soft delete (DoD)."""

from http import HTTPStatus
from uuid import UUID

from dmr.test import DMRClient


def test_create_root_comment_and_listing(
    client: DMRClient,
    author_headers: dict[str, str],
    author_profile_id: UUID,
    mock_events: list,
) -> None:
    """Create root comment (depth=0) on a post and verify listing."""
    post_res = client.post(
        "/api/v1/posts/",
        data={"title": "Commentable Post", "body": "Post Body"},
        **author_headers,
    )
    post_id = post_res.json()["id"]

    # 1. Create root comment
    comment_payload = {"body": "This is a great root comment!"}
    c_res = client.post(
        f"/api/v1/posts/{post_id}/comments/",
        data=comment_payload,
        **author_headers,
    )
    assert c_res.status_code == HTTPStatus.CREATED
    c_data = c_res.json()
    assert c_data["body"] == comment_payload["body"]
    assert c_data["depth"] == 0
    assert c_data["parent_id"] is None
    assert c_data["post_id"] == post_id
    assert c_data["author"]["id"] == str(author_profile_id)

    # 2. Check post comments_count incremented
    p_get = client.get(f"/api/v1/posts/{post_id}/")
    assert p_get.json()["comments_count"] == 1

    # 3. List comments on post
    list_res = client.get(f"/api/v1/posts/{post_id}/comments/")
    assert list_res.status_code == HTTPStatus.OK
    list_data = list_res.json()
    assert list_data["count"] == 1
    assert list_data["results"][0]["id"] == c_data["id"]


def test_comment_depth_enforcement_dod(
    client: DMRClient,
    author_headers: dict[str, str],
) -> None:
    """Verify 3-tier depth limit (DoD):

    Root (depth=0) -> Reply 1 (depth=1) -> Reply 2 (depth=2) -> Reply 3 (depth=3)
    Reply 4 (attempting depth=4) MUST return HTTP 400 Bad Request!
    """
    post_res = client.post(
        "/api/v1/posts/",
        data={"title": "Depth Test Post", "body": "Post Body"},
        **author_headers,
    )
    post_id = post_res.json()["id"]

    # Layer 0: Root comment
    r0 = client.post(
        f"/api/v1/posts/{post_id}/comments/",
        data={"body": "Level 0 Root"},
        **author_headers,
    )
    assert r0.status_code == HTTPStatus.CREATED
    c0_id = r0.json()["id"]
    assert r0.json()["depth"] == 0

    # Layer 1: Reply to Root
    r1 = client.post(
        f"/api/v1/comments/{c0_id}/replies/",
        data={"body": "Level 1 Reply"},
        **author_headers,
    )
    assert r1.status_code == HTTPStatus.CREATED
    c1_id = r1.json()["id"]
    assert r1.json()["depth"] == 1

    # Layer 2: Reply to Level 1
    r2 = client.post(
        f"/api/v1/comments/{c1_id}/replies/",
        data={"body": "Level 2 Reply"},
        **author_headers,
    )
    assert r2.status_code == HTTPStatus.CREATED
    c2_id = r2.json()["id"]
    assert r2.json()["depth"] == 2

    # Layer 3: Reply to Level 2 (allowed, depth=3)
    r3 = client.post(
        f"/api/v1/comments/{c2_id}/replies/",
        data={"body": "Level 3 Reply (Max depth allowed)"},
        **author_headers,
    )
    assert r3.status_code == HTTPStatus.CREATED
    c3_id = r3.json()["id"]
    assert r3.json()["depth"] == 3

    # Layer 4: Reply to Level 3 -> MUST FAIL with HTTP 400 (MAX_DEPTH_EXCEEDED)
    r4 = client.post(
        f"/api/v1/comments/{c3_id}/replies/",
        data={"body": "Level 4 Reply (Exceeds depth)"},
        **author_headers,
    )
    assert r4.status_code == HTTPStatus.BAD_REQUEST
    error_data = r4.json()
    assert "MAX_DEPTH_EXCEEDED" in str(error_data) or "3 levels" in str(error_data)


def test_tree_preserving_soft_delete(
    client: DMRClient,
    author_headers: dict[str, str],
) -> None:
    """When a comment has children, delete marks body as [deleted] to preserve tree."""
    post_res = client.post(
        "/api/v1/posts/",
        data={"title": "Delete Tree Post", "body": "Post Body"},
        **author_headers,
    )
    post_id = post_res.json()["id"]

    # Root comment
    r0 = client.post(
        f"/api/v1/posts/{post_id}/comments/",
        data={"body": "Parent comment with valuable replies"},
        **author_headers,
    )
    c0_id = r0.json()["id"]

    # Child reply
    client.post(
        f"/api/v1/comments/{c0_id}/replies/",
        data={"body": "Child reply that keeps thread alive"},
        **author_headers,
    )

    # Delete parent comment
    del_res = client.delete(f"/api/v1/comments/{c0_id}/", **author_headers)
    assert del_res.status_code == HTTPStatus.NO_CONTENT

    # Fetch parent comment detail: body should be [deleted] and author nullified
    get_res = client.get(f"/api/v1/comments/{c0_id}/")
    assert get_res.status_code == HTTPStatus.OK
    c0_data = get_res.json()
    assert c0_data["is_deleted"] is True
    assert c0_data["body"] == "[deleted]"
    assert c0_data["author"]["id"] is None


def test_voting_on_comment(
    client: DMRClient,
    author_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    """Upvote, downvote, and remove vote on comment."""
    post_res = client.post(
        "/api/v1/posts/",
        data={"title": "Voting Post", "body": "Body"},
        **author_headers,
    )
    post_id = post_res.json()["id"]

    c_res = client.post(
        f"/api/v1/posts/{post_id}/comments/",
        data={"body": "Vote for me!"},
        **author_headers,
    )
    comment_id = c_res.json()["id"]

    # 1. Other user upvotes (+1)
    up_res = client.post(
        f"/api/v1/comments/{comment_id}/vote/",
        data={"value": 1},
        **other_headers,
    )
    assert up_res.status_code == HTTPStatus.OK
    up_data = up_res.json()
    assert up_data["upvotes_count"] == 1
    assert up_data["downvotes_count"] == 0
    assert up_data["popularity_score"] == 1

    # 2. Other user flips to downvote (-1)
    down_res = client.post(
        f"/api/v1/comments/{comment_id}/vote/",
        data={"value": -1},
        **other_headers,
    )
    assert down_res.status_code == HTTPStatus.OK
    down_data = down_res.json()
    assert down_data["upvotes_count"] == 0
    assert down_data["downvotes_count"] == 1
    assert down_data["popularity_score"] == -1

    # 3. Other user removes vote (0)
    zero_res = client.post(
        f"/api/v1/comments/{comment_id}/vote/",
        data={"value": 0},
        **other_headers,
    )
    assert zero_res.status_code == HTTPStatus.OK
    zero_data = zero_res.json()
    assert zero_data["upvotes_count"] == 0
    assert zero_data["downvotes_count"] == 0
    assert zero_data["popularity_score"] == 0

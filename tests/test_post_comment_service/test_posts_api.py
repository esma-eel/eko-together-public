"""Tests for Post Service API endpoints and business logic."""

from http import HTTPStatus
from uuid import UUID, uuid4

from dmr.test import DMRClient


def test_create_post_unauthenticated(client: DMRClient) -> None:
    """Anonymous user cannot create a post."""
    payload = {
        "title": "Unauthenticated Post",
        "body": "Should fail with 401",
    }
    response = client.post("/api/v1/posts/", data=payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_create_post_success(
    client: DMRClient,
    author_headers: dict[str, str],
    author_profile_id: UUID,
    mock_events: list,
) -> None:
    """Authenticated user creates a post with tags and image URL."""
    payload = {
        "title": "Advanced Python & Distributed Systems",
        "body": "Here is an in-depth guide on event-driven architectures with RabbitMQ.",
        "image": "https://cdn.eko-together.com/uploads/posts/diagram.png",
        "tags": ["Python", "Distributed Systems", "MongoDB"],
        "visibility": "PUBLIC",
        "comment_permission": "ANYONE",
    }
    response = client.post("/api/v1/posts/", data=payload, **author_headers)
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data["title"] == payload["title"]
    assert data["body"] == payload["body"]
    assert data["image"] == payload["image"]
    assert data["author_profile_id"] == str(author_profile_id)
    assert data["visibility"] == "PUBLIC"
    assert data["comment_permission"] == "ANYONE"
    assert data["is_deleted"] is False
    assert data["is_archived"] is False
    assert data["comments_count"] == 0

    # Verify tags normalized
    slugs = [t["slug"] for t in data["tags"]]
    assert "python" in slugs
    assert "distributed-systems" in slugs
    assert "mongodb" in slugs

    # Verify post.created event emitted
    assert len(mock_events) == 1
    assert mock_events[0].event_type == "post.created"
    assert str(mock_events[0].author_profile_id) == str(author_profile_id)


def test_list_posts_with_filtering(
    client: DMRClient,
    author_headers: dict[str, str],
    author_profile_id: UUID,
    other_headers: dict[str, str],
    other_profile_id: UUID,
) -> None:
    """List posts and filter by author and tag."""
    # Create post 1 by author
    client.post(
        "/api/v1/posts/",
        data={
            "title": "Post One by Author",
            "body": "Content 1",
            "tags": ["Django", "Web"],
        },
        **author_headers,
    )
    # Create post 2 by other
    client.post(
        "/api/v1/posts/",
        data={
            "title": "Post Two by Other",
            "body": "Content 2",
            "tags": ["FastAPI", "Web"],
        },
        **other_headers,
    )

    # 1. List all public posts
    res_all = client.get("/api/v1/posts/")
    assert res_all.status_code == HTTPStatus.OK
    assert res_all.json()["count"] == 2

    # 2. Filter by author
    res_author = client.get(f"/api/v1/posts/?author_profile_id={author_profile_id}")
    assert res_author.status_code == HTTPStatus.OK
    assert res_author.json()["count"] == 1
    assert res_author.json()["results"][0]["title"] == "Post One by Author"

    # 3. Filter by tag
    res_tag = client.get("/api/v1/posts/?tag=django")
    assert res_tag.status_code == HTTPStatus.OK
    assert res_tag.json()["count"] == 1
    assert res_tag.json()["results"][0]["title"] == "Post One by Author"


def test_get_post_detail(
    client: DMRClient,
    author_headers: dict[str, str],
) -> None:
    """Retrieve existing post and return 404 for unknown post."""
    create_res = client.post(
        "/api/v1/posts/",
        data={"title": "Detail Target", "body": "Detail Body"},
        **author_headers,
    )
    post_id = create_res.json()["id"]

    # Valid get
    get_res = client.get(f"/api/v1/posts/{post_id}/")
    assert get_res.status_code == HTTPStatus.OK
    assert get_res.json()["id"] == post_id

    # 404 for random UUID
    unknown_id = str(uuid4())
    missing_res = client.get(f"/api/v1/posts/{unknown_id}/")
    assert missing_res.status_code == HTTPStatus.NOT_FOUND


def test_update_post_permissions(
    client: DMRClient,
    author_headers: dict[str, str],
    other_headers: dict[str, str],
) -> None:
    """Only the post author can update post content."""
    create_res = client.post(
        "/api/v1/posts/",
        data={"title": "Original Title", "body": "Original Body"},
        **author_headers,
    )
    post_id = create_res.json()["id"]

    # Non-author tries to update -> 403 Forbidden
    patch_forbidden = client.patch(
        f"/api/v1/posts/{post_id}/",
        data={"title": "Hacked Title"},
        **other_headers,
    )
    assert patch_forbidden.status_code == HTTPStatus.FORBIDDEN

    # Author updates -> 200 OK
    patch_ok = client.patch(
        f"/api/v1/posts/{post_id}/",
        data={"title": "Updated Title", "body": "Updated Body"},
        **author_headers,
    )
    assert patch_ok.status_code == HTTPStatus.OK
    assert patch_ok.json()["title"] == "Updated Title"
    assert patch_ok.json()["body"] == "Updated Body"


def test_soft_delete_post(
    client: DMRClient,
    author_headers: dict[str, str],
    other_headers: dict[str, str],
    mock_events: list,
) -> None:
    """Soft delete sets is_deleted=True and emits post.deleted event."""
    create_res = client.post(
        "/api/v1/posts/",
        data={"title": "To be deleted", "body": "Delete me"},
        **author_headers,
    )
    post_id = create_res.json()["id"]

    # Stranger cannot delete
    del_forbidden = client.delete(f"/api/v1/posts/{post_id}/", **other_headers)
    assert del_forbidden.status_code == HTTPStatus.FORBIDDEN

    # Author can delete
    del_ok = client.delete(f"/api/v1/posts/{post_id}/", **author_headers)
    assert del_ok.status_code == HTTPStatus.NO_CONTENT

    # Verify is_deleted: hidden from public (404) but visible to author (200)
    anon_res = client.get(f"/api/v1/posts/{post_id}/")
    assert anon_res.status_code == HTTPStatus.NOT_FOUND

    author_res = client.get(f"/api/v1/posts/{post_id}/", **author_headers)
    assert author_res.status_code == HTTPStatus.OK
    assert author_res.json()["is_deleted"] is True


def test_archive_post(
    client: DMRClient,
    author_headers: dict[str, str],
) -> None:
    """Toggle post archiving."""
    create_res = client.post(
        "/api/v1/posts/",
        data={"title": "Archive Target", "body": "Archive Body"},
        **author_headers,
    )
    post_id = create_res.json()["id"]

    archive_res = client.post(
        f"/api/v1/posts/{post_id}/archive/",
        data={"is_archived": True},
        **author_headers,
    )
    assert archive_res.status_code == HTTPStatus.OK
    assert archive_res.json()["is_archived"] is True

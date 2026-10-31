"""Tests for Forum CRUD, discovery, and lifecycle management."""

from http import HTTPStatus
from uuid import UUID

import pytest
from dmr.test import DMRClient

from services.forum_service.apps.forums.models import (
    Forum,
    ForumMember,
    MemberRoleChoices,
    MemberStatusChoices,
)


@pytest.mark.django_db
def test_create_forum_success(
    client: DMRClient,
    owner_headers: dict[str, str],
    owner_profile_id: UUID,
) -> None:
    """Validate forum creation enrolls creator as owner and initializes members count."""
    payload = {
        "title": "Backend Engineering & Go",
        "slug": "backend-go",
        "description": "High performance concurrent services.",
        "rules": "1. Keep code clean.",
        "avatar": "https://cdn.example.com/avatar.png",
        "cover_image": "https://cdn.example.com/cover.png",
        "require_approval_to_join": False,
        "post_permission": "ALL_MEMBERS",
        "is_comments_locked": False,
    }
    response = client.post("/api/v1/forums/", data=payload, **owner_headers)
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data["title"] == "Backend Engineering & Go"
    assert data["slug"] == "backend-go"
    assert data["owner_profile_id"] == str(owner_profile_id)
    assert data["members_count"] == 1

    # Verify database state
    forum = Forum.objects.get(slug="backend-go")
    assert forum.owner_profile_id == owner_profile_id
    member = ForumMember.objects.get(forum=forum, user_profile_id=owner_profile_id)
    assert member.role == MemberRoleChoices.OWNER
    assert member.status == MemberStatusChoices.APPROVED


@pytest.mark.django_db
def test_create_forum_duplicate_slug(
    client: DMRClient,
    sample_forum: Forum,
    owner_headers: dict[str, str],
) -> None:
    """Validate duplicate slug returns 409 Conflict."""
    payload = {
        "title": "Duplicate Distributed",
        "slug": sample_forum.slug,
    }
    response = client.post("/api/v1/forums/", data=payload, **owner_headers)
    assert response.status_code == HTTPStatus.CONFLICT


@pytest.mark.django_db
def test_list_and_search_forums(
    client: DMRClient,
    sample_forum: Forum,
) -> None:
    """Validate public listing and searching of forums."""
    # List all
    response = client.get("/api/v1/forums/")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["count"] >= 1
    assert any(f["slug"] == sample_forum.slug for f in data["results"])

    # Search match
    response = client.get("/api/v1/forums/?search=distributed")
    assert response.status_code == HTTPStatus.OK
    assert response.json()["count"] >= 1

    # Search non-match
    response = client.get("/api/v1/forums/?search=nonexistenttermxyz")
    assert response.status_code == HTTPStatus.OK
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_get_forum_detail_membership_enrichment(
    client: DMRClient,
    sample_forum: Forum,
    member_headers: dict[str, str],
    stranger_headers: dict[str, str],
) -> None:
    """Validate forum detail enriches response with requester's role and status."""
    # Member view
    resp_member = client.get(
        f"/api/v1/forums/{sample_forum.slug}/",
        **member_headers,
    )
    assert resp_member.status_code == HTTPStatus.OK
    data_member = resp_member.json()
    assert data_member["is_member"] is True
    assert data_member["my_role"] == MemberRoleChoices.MEMBER
    assert data_member["my_status"] == MemberStatusChoices.APPROVED

    # Stranger view
    resp_stranger = client.get(
        f"/api/v1/forums/{sample_forum.slug}/",
        **stranger_headers,
    )
    assert resp_stranger.status_code == HTTPStatus.OK
    data_stranger = resp_stranger.json()
    assert data_stranger["is_member"] is False
    assert data_stranger["my_role"] is None

    # Anonymous view
    resp_anon = client.get(f"/api/v1/forums/{sample_forum.slug}/")
    assert resp_anon.status_code == HTTPStatus.OK
    assert resp_anon.json()["is_member"] is False


@pytest.mark.django_db
def test_update_forum_permissions(
    client: DMRClient,
    sample_forum: Forum,
    owner_headers: dict[str, str],
    admin_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    """Validate owner and admin can update forum settings, while standard members cannot."""
    payload = {
        "post_permission": "ADMINS_ONLY",
        "is_comments_locked": True,
    }

    # Member fails (403)
    resp_member = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/",
        data=payload,
        **member_headers,
    )
    assert resp_member.status_code == HTTPStatus.FORBIDDEN

    # Admin succeeds (200)
    resp_admin = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/",
        data=payload,
        **admin_headers,
    )
    assert resp_admin.status_code == HTTPStatus.OK
    assert resp_admin.json()["post_permission"] == "ADMINS_ONLY"
    assert resp_admin.json()["is_comments_locked"] is True

    # Owner succeeds (200)
    resp_owner = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/",
        data={"is_comments_locked": False},
        **owner_headers,
    )
    assert resp_owner.status_code == HTTPStatus.OK
    assert resp_owner.json()["is_comments_locked"] is False


@pytest.mark.django_db
def test_delete_forum_owner_only(
    client: DMRClient,
    sample_forum: Forum,
    owner_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    """Validate only the forum owner can permanently delete the forum."""
    # Admin attempt fails (403)
    resp_admin = client.delete(
        f"/api/v1/forums/{sample_forum.slug}/",
        **admin_headers,
    )
    assert resp_admin.status_code == HTTPStatus.FORBIDDEN
    assert Forum.objects.filter(slug=sample_forum.slug).exists()

    # Owner attempt succeeds (204)
    resp_owner = client.delete(
        f"/api/v1/forums/{sample_forum.slug}/",
        **owner_headers,
    )
    assert resp_owner.status_code == HTTPStatus.NO_CONTENT
    assert not Forum.objects.filter(slug=sample_forum.slug).exists()

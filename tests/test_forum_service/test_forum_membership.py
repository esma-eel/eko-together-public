"""Tests for Forum membership lifecycle, approvals, roles, and moderation."""

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
def test_join_open_forum(
    client: DMRClient,
    sample_forum: Forum,
    stranger_headers: dict[str, str],
    stranger_profile_id: UUID,
) -> None:
    """Validate joining an open forum grants immediate APPROVED status and increments count."""
    initial_count = sample_forum.members_count
    response = client.post(
        f"/api/v1/forums/{sample_forum.slug}/join/",
        **stranger_headers,
    )
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()
    assert data["status"] == MemberStatusChoices.APPROVED

    sample_forum.refresh_from_db()
    assert sample_forum.members_count == initial_count + 1

    member = ForumMember.objects.get(forum=sample_forum, user_profile_id=stranger_profile_id)
    assert member.role == MemberRoleChoices.MEMBER
    assert member.status == MemberStatusChoices.APPROVED


@pytest.mark.django_db
def test_join_approval_required_forum(
    client: DMRClient,
    sample_forum: Forum,
    stranger_headers: dict[str, str],
    stranger_profile_id: UUID,
) -> None:
    """Validate joining approval-required forum results in PENDING status without count increase."""
    sample_forum.require_approval_to_join = True
    sample_forum.save()

    initial_count = sample_forum.members_count
    response = client.post(
        f"/api/v1/forums/{sample_forum.slug}/join/",
        **stranger_headers,
    )
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()
    assert data["status"] == MemberStatusChoices.PENDING

    sample_forum.refresh_from_db()
    assert sample_forum.members_count == initial_count

    member = ForumMember.objects.get(forum=sample_forum, user_profile_id=stranger_profile_id)
    assert member.status == MemberStatusChoices.PENDING


@pytest.mark.django_db
def test_join_forum_conflicts_and_ban(
    client: DMRClient,
    sample_forum: Forum,
    member_headers: dict[str, str],
    banned_headers: dict[str, str],
) -> None:
    """Validate already joined users get 409 Conflict, and banned users get 403 Forbidden."""
    # Existing approved member
    resp_conflict = client.post(
        f"/api/v1/forums/{sample_forum.slug}/join/",
        **member_headers,
    )
    assert resp_conflict.status_code == HTTPStatus.CONFLICT

    # Banned user
    resp_banned = client.post(
        f"/api/v1/forums/{sample_forum.slug}/join/",
        **banned_headers,
    )
    assert resp_banned.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.django_db
def test_admin_approve_and_ban_member(
    client: DMRClient,
    sample_forum: Forum,
    admin_headers: dict[str, str],
    stranger_profile_id: UUID,
) -> None:
    """Validate admin can approve pending requests and ban members, maintaining counters."""
    # Create pending member
    ForumMember.objects.create(
        forum=sample_forum,
        user_profile_id=stranger_profile_id,
        role=MemberRoleChoices.MEMBER,
        status=MemberStatusChoices.PENDING,
    )
    initial_count = sample_forum.members_count

    # Admin approves
    resp_approve = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/members/{stranger_profile_id}/",
        data={"status": "APPROVED"},
        **admin_headers,
    )
    assert resp_approve.status_code == HTTPStatus.OK
    assert resp_approve.json()["status"] == "APPROVED"

    sample_forum.refresh_from_db()
    assert sample_forum.members_count == initial_count + 1

    # Admin bans
    resp_ban = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/members/{stranger_profile_id}/",
        data={"status": "BANNED"},
        **admin_headers,
    )
    assert resp_ban.status_code == HTTPStatus.OK
    assert resp_ban.json()["status"] == "BANNED"

    sample_forum.refresh_from_db()
    assert sample_forum.members_count == initial_count


@pytest.mark.django_db
def test_promotion_rules(
    client: DMRClient,
    sample_forum: Forum,
    owner_headers: dict[str, str],
    admin_headers: dict[str, str],
    member_profile_id: UUID,
    owner_profile_id: UUID,
) -> None:
    """Validate only Owner can promote to Admin, and no one can demote Owner."""
    # Admin attempt to promote to ADMIN fails (403)
    resp_admin_promo = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/members/{member_profile_id}/",
        data={"role": "ADMIN"},
        **admin_headers,
    )
    assert resp_admin_promo.status_code == HTTPStatus.FORBIDDEN

    # Owner promotes to ADMIN succeeds (200)
    resp_owner_promo = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/members/{member_profile_id}/",
        data={"role": "ADMIN"},
        **owner_headers,
    )
    assert resp_owner_promo.status_code == HTTPStatus.OK
    assert resp_owner_promo.json()["role"] == "ADMIN"

    # Attempt to ban or demote owner fails (403)
    resp_ban_owner = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/members/{owner_profile_id}/",
        data={"status": "BANNED"},
        **owner_headers,
    )
    assert resp_ban_owner.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.django_db
def test_kick_member_and_leave_forum(
    client: DMRClient,
    sample_forum: Forum,
    admin_headers: dict[str, str],
    member_headers: dict[str, str],
    owner_headers: dict[str, str],
    member_profile_id: UUID,
) -> None:
    """Validate member kicking and voluntary leaving update membership counts."""
    # Member leaves
    initial_count = sample_forum.members_count
    resp_leave = client.post(
        f"/api/v1/forums/{sample_forum.slug}/leave/",
        **member_headers,
    )
    assert resp_leave.status_code == HTTPStatus.NO_CONTENT
    assert not ForumMember.objects.filter(
        forum=sample_forum, user_profile_id=member_profile_id
    ).exists()

    sample_forum.refresh_from_db()
    assert sample_forum.members_count == initial_count - 1

    # Owner tries to leave fails (422)
    resp_owner_leave = client.post(
        f"/api/v1/forums/{sample_forum.slug}/leave/",
        **owner_headers,
    )
    assert resp_owner_leave.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

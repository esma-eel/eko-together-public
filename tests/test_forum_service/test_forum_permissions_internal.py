"""Tests for inter-service posting permission verification endpoints."""

from http import HTTPStatus
from uuid import UUID

import pytest
from dmr.test import DMRClient

from services.forum_service.apps.forums.models import Forum, PostPermissionChoices


@pytest.mark.django_db
def test_internal_permission_check_all_members(
    client: DMRClient,
    sample_forum: Forum,
    member_profile_id: UUID,
    banned_profile_id: UUID,
) -> None:
    """Validate internal permission check for ALL_MEMBERS mode."""
    # Member allowed
    resp_member = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={member_profile_id}"
    )
    assert resp_member.status_code == HTTPStatus.OK
    data_member = resp_member.json()
    assert data_member["can_post"] is True
    assert data_member["user_role"] == "MEMBER"
    assert data_member["user_status"] == "APPROVED"

    # Banned member denied
    resp_banned = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={banned_profile_id}"
    )
    assert resp_banned.status_code == HTTPStatus.OK
    data_banned = resp_banned.json()
    assert data_banned["can_post"] is False
    assert data_banned["user_status"] == "BANNED"


@pytest.mark.django_db
def test_internal_permission_check_admins_only_and_read_only(
    client: DMRClient,
    sample_forum: Forum,
    admin_profile_id: UUID,
    member_profile_id: UUID,
) -> None:
    """Validate internal permission check for ADMINS_ONLY and NO_ONE policies."""
    sample_forum.post_permission = PostPermissionChoices.ADMINS_ONLY
    sample_forum.save()

    # Admin allowed
    resp_admin = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={admin_profile_id}"
    )
    assert resp_admin.status_code == HTTPStatus.OK
    assert resp_admin.json()["can_post"] is True

    # Standard member denied
    resp_member = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={member_profile_id}"
    )
    assert resp_member.status_code == HTTPStatus.OK
    assert resp_member.json()["can_post"] is False

    # Read-only forum (NO_ONE)
    sample_forum.post_permission = PostPermissionChoices.NO_ONE
    sample_forum.save()

    resp_read_only = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={admin_profile_id}"
    )
    assert resp_read_only.status_code == HTTPStatus.OK
    assert resp_read_only.json()["can_post"] is False
    assert "read-only" in resp_read_only.json()["reason"].lower()


@pytest.mark.django_db
def test_internal_permission_admin_visibility_flag(
    client: DMRClient,
    sample_forum: Forum,
    admin_profile_id: UUID,
    member_profile_id: UUID,
) -> None:
    """Validate only admins can publish admin-visibility posts."""
    # Member denied for admin_visibility=ADMINS_ONLY
    resp_member = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={member_profile_id}&admin_visibility=ADMINS_ONLY"
    )
    assert resp_member.status_code == HTTPStatus.OK
    assert resp_member.json()["can_post"] is False

    # Admin allowed
    resp_admin = client.get(
        f"/internal/forums/{sample_forum.id}/check-permission/?user_profile_id={admin_profile_id}&admin_visibility=ADMINS_ONLY"
    )
    assert resp_admin.status_code == HTTPStatus.OK
    assert resp_admin.json()["can_post"] is True

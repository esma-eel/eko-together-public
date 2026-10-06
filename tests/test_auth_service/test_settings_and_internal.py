"""Tests for User Settings and Internal Inter-Service endpoints."""

from http import HTTPStatus

import pytest
from dmr.test import DMRClient

from services.auth_user_service.apps.accounts.models import (
    RelationStatusChoices,
    User,
    UserRelation,
)


@pytest.mark.django_db
def test_privacy_settings_get(
    client: DMRClient, user_a: User, auth_headers_a: dict[str, str]
) -> None:
    """GET /api/v1/users/settings/privacy/ returns current defaults."""
    response = client.get("/api/v1/users/settings/privacy/", **auth_headers_a)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["is_private_account"] is False
    assert data["default_post_visibility"] == "PUBLIC"
    assert data["default_comment_permission"] == "ANYONE"


@pytest.mark.django_db
def test_privacy_settings_patch(
    client: DMRClient, user_a: User, auth_headers_a: dict[str, str]
) -> None:
    """PATCH /api/v1/users/settings/privacy/ updates preferences."""
    payload = {
        "is_private_account": True,
        "default_post_visibility": "FOLLOWERS_ONLY",
        "default_comment_permission": "FOLLOWERS_ONLY",
    }
    response = client.patch("/api/v1/users/settings/privacy/", data=payload, **auth_headers_a)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["is_private_account"] is True
    assert data["default_post_visibility"] == "FOLLOWERS_ONLY"
    assert data["default_comment_permission"] == "FOLLOWERS_ONLY"

    # Verify DB update
    user_a.profile.refresh_from_db()
    assert user_a.profile.is_private is True
    assert user_a.profile.default_post_visibility == "FOLLOWERS_ONLY"


@pytest.mark.django_db
def test_internal_relation_check(
    client: DMRClient,
    user_a: User,
    user_b: User,
    private_user: User,
) -> None:
    """GET /internal/relations/check/ evaluates relations for downstream microservices."""
    # 1. No relationship -> is_following: False, status: NONE
    none_resp = client.get(
        f"/internal/relations/check/?follower_id={user_a.profile.id}&target_id={user_b.profile.id}"
    )
    assert none_resp.status_code == HTTPStatus.OK
    assert none_resp.json() == {"is_following": False, "status": "NONE"}

    # 2. Accepted relationship -> is_following: True, status: ACCEPTED
    UserRelation.objects.create(
        follower_profile=user_a.profile,
        following_profile=user_b.profile,
        status=RelationStatusChoices.ACCEPTED,
    )
    acc_resp = client.get(
        f"/internal/relations/check/?follower_id={user_a.profile.id}&target_id={user_b.profile.id}"
    )
    assert acc_resp.status_code == HTTPStatus.OK
    assert acc_resp.json() == {"is_following": True, "status": "ACCEPTED"}

    # 3. Pending relationship -> is_following: False, status: PENDING
    UserRelation.objects.create(
        follower_profile=user_a.profile,
        following_profile=private_user.profile,
        status=RelationStatusChoices.PENDING,
    )
    pend_resp = client.get(
        f"/internal/relations/check/?follower_id={user_a.profile.id}&target_id={private_user.profile.id}"
    )
    assert pend_resp.status_code == HTTPStatus.OK
    assert pend_resp.json() == {"is_following": False, "status": "PENDING"}

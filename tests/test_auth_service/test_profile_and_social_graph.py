"""Tests for Profiles and Social Graph endpoints (/api/v1/profiles/).

Validates follow lifecycle, private profile approval flow, and privacy-filtered views.
"""

from http import HTTPStatus

import pytest
from dmr.test import DMRClient

from services.auth_user_service.apps.accounts.models import (
    RelationStatusChoices,
    User,
    UserRelation,
)


@pytest.mark.django_db
def test_get_my_profile(client: DMRClient, user_a: User, auth_headers_a: dict[str, str]) -> None:
    """GET /api/v1/profiles/me/ returns authenticated user's profile and preferences."""
    response = client.get("/api/v1/profiles/me/", **auth_headers_a)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["username"] == "alice"
    assert data["display_name"] == "Alice Smith"
    assert data["bio"] == "Hello, I am Alice."
    assert data["is_private"] is False
    assert data["stats"]["followers_count"] == 0
    assert data["preferences"]["default_post_visibility"] == "PUBLIC"


@pytest.mark.django_db
def test_update_my_profile(client: DMRClient, user_a: User, auth_headers_a: dict[str, str]) -> None:
    """PATCH /api/v1/profiles/me/ updates editable fields."""
    payload = {
        "display_name": "Alice Wonderland",
        "bio": "Updated bio text.",
        "is_private": True,
    }
    response = client.patch("/api/v1/profiles/me/", data=payload, **auth_headers_a)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["display_name"] == "Alice Wonderland"
    assert data["bio"] == "Updated bio text."
    assert data["is_private"] is True

    # Verify DB update
    user_a.profile.refresh_from_db()
    assert user_a.profile.display_name == "Alice Wonderland"
    assert user_a.profile.is_private is True


@pytest.mark.django_db
def test_public_profile_view_by_anonymous(client: DMRClient, user_a: User) -> None:
    """Public profile reveals full details and bio to unauthenticated viewers."""
    response = client.get(f"/api/v1/profiles/{user_a.username}/")
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["username"] == "alice"
    assert data["bio"] == "Hello, I am Alice."
    assert data["viewer_status"] == "NONE"


@pytest.mark.django_db
def test_private_profile_view_by_non_follower(
    client: DMRClient,
    private_user: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Private profile hides biography and details from non-followers."""
    response = client.get(f"/api/v1/profiles/{private_user.username}/", **auth_headers_a)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["username"] == "clara_private"
    assert data["is_private"] is True
    assert data["bio"] is None  # Bio hidden for private profile
    assert data["viewer_status"] == "NONE"


@pytest.mark.django_db
def test_follow_public_user_immediate_accept(
    client: DMRClient,
    user_a: User,
    user_b: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Following a public profile immediately creates an ACCEPTED relation."""
    response = client.post(
        f"/api/v1/profiles/{user_b.profile.id}/follow/",
        **auth_headers_a,
    )
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    assert data["status"] == "ACCEPTED"
    assert data["following_profile_id"] == str(user_b.profile.id)

    # Verify relationship in DB
    rel = UserRelation.objects.get(
        follower_profile=user_a.profile,
        following_profile=user_b.profile,
    )
    assert rel.status == RelationStatusChoices.ACCEPTED


@pytest.mark.django_db
def test_follow_self_rejected(
    client: DMRClient,
    user_a: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Attempting to follow one's own profile is rejected with 422."""
    response = client.post(
        f"/api/v1/profiles/{user_a.profile.id}/follow/",
        **auth_headers_a,
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.django_db
def test_private_profile_full_approval_flow(
    client: DMRClient,
    user_a: User,
    private_user: User,
    auth_headers_a: dict[str, str],
    auth_headers_private: dict[str, str],
) -> None:
    """Definition of Done (DoD) Test:

    1. User A follows private user -> status PENDING.
    2. User A views profile -> bio hidden, viewer_status: PENDING.
    3. Private user views pending follow requests list.
    4. Private user approves follow request.
    5. User A views profile again -> bio visible, viewer_status: ACCEPTED.
    """
    # 1. User A requests to follow Clara (private)
    follow_resp = client.post(
        f"/api/v1/profiles/{private_user.profile.id}/follow/",
        **auth_headers_a,
    )
    assert follow_resp.status_code == HTTPStatus.CREATED
    follow_data = follow_resp.json()
    assert follow_data["status"] == "PENDING"
    relation_id = follow_data["relation_id"]

    # 2. User A views profile -> bio still hidden
    view_pending = client.get(f"/api/v1/profiles/{private_user.username}/", **auth_headers_a)
    assert view_pending.status_code == HTTPStatus.OK
    assert view_pending.json()["bio"] is None
    assert view_pending.json()["viewer_status"] == "PENDING"

    # 3. Clara lists follow requests
    requests_resp = client.get("/api/v1/profiles/me/follow-requests/", **auth_headers_private)
    assert requests_resp.status_code == HTTPStatus.OK
    requests_data = requests_resp.json()
    assert requests_data["count"] == 1
    assert requests_data["results"][0]["relation_id"] == relation_id
    assert requests_data["results"][0]["follower"]["username"] == "alice"

    # 4. Clara APPROVES the follow request
    action_resp = client.post(
        f"/api/v1/profiles/me/follow-requests/{relation_id}/",
        data={"action": "APPROVE"},
        **auth_headers_private,
    )
    assert action_resp.status_code == HTTPStatus.OK
    assert action_resp.json()["status"] == "ACCEPTED"

    # 5. User A views Clara's profile again -> bio is now accessible!
    view_approved = client.get(f"/api/v1/profiles/{private_user.username}/", **auth_headers_a)
    assert view_approved.status_code == HTTPStatus.OK
    assert view_approved.json()["bio"] == "Confidential profile notes."
    assert view_approved.json()["viewer_status"] == "ACCEPTED"


@pytest.mark.django_db
def test_private_profile_reject_flow(
    client: DMRClient,
    user_a: User,
    private_user: User,
    auth_headers_a: dict[str, str],
    auth_headers_private: dict[str, str],
) -> None:
    """Private user can REJECT a pending follow request."""
    # User A requests to follow
    follow_resp = client.post(
        f"/api/v1/profiles/{private_user.profile.id}/follow/",
        **auth_headers_a,
    )
    relation_id = follow_resp.json()["relation_id"]

    # Clara REJECTS request
    action_resp = client.post(
        f"/api/v1/profiles/me/follow-requests/{relation_id}/",
        data={"action": "REJECT"},
        **auth_headers_private,
    )
    assert action_resp.status_code == HTTPStatus.OK
    assert action_resp.json()["status"] == "REJECTED"


@pytest.mark.django_db
def test_unfollow_user(
    client: DMRClient,
    user_a: User,
    user_b: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Unfollowing removes the relationship edge."""
    # Follow
    client.post(f"/api/v1/profiles/{user_b.profile.id}/follow/", **auth_headers_a)
    assert UserRelation.objects.filter(
        follower_profile=user_a.profile,
        following_profile=user_b.profile,
    ).exists()

    # Unfollow
    unfollow_resp = client.delete(
        f"/api/v1/profiles/{user_b.profile.id}/unfollow/", **auth_headers_a
    )
    assert unfollow_resp.status_code == HTTPStatus.NO_CONTENT

    # Verify edge deleted
    assert not UserRelation.objects.filter(
        follower_profile=user_a.profile,
        following_profile=user_b.profile,
    ).exists()


@pytest.mark.django_db
def test_followers_and_following_lists(
    client: DMRClient,
    user_a: User,
    user_b: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Verify followers and following pagination endpoints."""
    # Alice follows Bob
    client.post(f"/api/v1/profiles/{user_b.profile.id}/follow/", **auth_headers_a)

    # Bob's followers
    followers_resp = client.get(f"/api/v1/profiles/{user_b.profile.id}/followers/")
    assert followers_resp.status_code == HTTPStatus.OK
    f_data = followers_resp.json()
    assert f_data["count"] == 1
    assert f_data["results"][0]["username"] == "alice"

    # Alice's following
    following_resp = client.get(f"/api/v1/profiles/{user_a.profile.id}/following/")
    assert following_resp.status_code == HTTPStatus.OK
    ing_data = following_resp.json()
    assert ing_data["count"] == 1
    assert ing_data["results"][0]["username"] == "bob"


@pytest.mark.django_db
def test_deactivated_user_profile_hidden_and_unfollowable(
    client: DMRClient,
    user_a: User,
    user_b: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Deactivated accounts are hidden from public profile lookups and cannot be followed."""
    user_b.is_active = False
    user_b.save(update_fields=["is_active"])

    # 1. Viewing profile returns 404
    resp = client.get(f"/api/v1/profiles/{user_b.username}/")
    assert resp.status_code == HTTPStatus.NOT_FOUND

    # 2. Attempting to follow deactivated user returns 404
    follow_resp = client.post(f"/api/v1/profiles/{user_b.profile.id}/follow/", **auth_headers_a)
    assert follow_resp.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.django_db
def test_deactivated_user_excluded_from_follower_lists(
    client: DMRClient,
    user_a: User,
    user_b: User,
    auth_headers_a: dict[str, str],
) -> None:
    """Deactivated users do not appear in followers or following lists."""
    # Alice follows Bob
    client.post(f"/api/v1/profiles/{user_b.profile.id}/follow/", **auth_headers_a)

    # Bob's followers before deactivation: count 1
    user_b.profile.refresh_from_db()
    assert user_b.profile.followers_count == 1

    # Deactivate Alice
    user_a.is_active = False
    user_a.save(update_fields=["is_active"])

    # Synchronize cached counters after account deactivation
    from services.auth_user_service.apps.accounts.services import sync_profile_counts
    sync_profile_counts(user_b.profile)
    assert user_b.profile.followers_count == 0

    # Followers list API excludes deactivated Alice
    followers_resp = client.get(f"/api/v1/profiles/{user_b.profile.id}/followers/")
    assert followers_resp.status_code == HTTPStatus.OK
    f_data = followers_resp.json()
    assert f_data["count"] == 0
    assert len(f_data["results"]) == 0


@pytest.mark.django_db
def test_counter_cache_lifecycle(
    user_a: User,
    user_b: User,
    private_user: User,
) -> None:
    """Verify followers_count and following_count are maintained atomically on UserProfile."""
    from services.auth_user_service.apps.accounts.services import (
        follow_user_profile,
        handle_follow_request_action,
        unfollow_user_profile,
    )

    # Initially zero
    assert user_a.profile.following_count == 0
    assert user_b.profile.followers_count == 0

    # 1. Follow public user (immediate ACCEPTED)
    follow_user_profile(user_a.profile, user_b.profile)
    user_a.profile.refresh_from_db()
    user_b.profile.refresh_from_db()
    assert user_a.profile.following_count == 1
    assert user_b.profile.followers_count == 1

    # 2. Unfollow public user (decrements counters)
    unfollow_user_profile(user_a.profile, user_b.profile)
    user_a.profile.refresh_from_db()
    user_b.profile.refresh_from_db()
    assert user_a.profile.following_count == 0
    assert user_b.profile.followers_count == 0

    # 3. Follow private user (PENDING does NOT increment counters)
    rel = follow_user_profile(user_a.profile, private_user.profile)
    user_a.profile.refresh_from_db()
    private_user.profile.refresh_from_db()
    assert user_a.profile.following_count == 0
    assert private_user.profile.followers_count == 0

    # 4. Approve private follow request (increments counters)
    handle_follow_request_action(private_user.profile, rel.id, "APPROVE")
    user_a.profile.refresh_from_db()
    private_user.profile.refresh_from_db()
    assert user_a.profile.following_count == 1
    assert private_user.profile.followers_count == 1


@pytest.mark.django_db
def test_db_check_constraint_prevents_self_follow(user_a: User) -> None:
    """Database CheckConstraint prevents inserting self-follow edge directly."""
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        UserRelation.objects.create(
            follower_profile=user_a.profile,
            following_profile=user_a.profile,
            status=RelationStatusChoices.ACCEPTED,
        )


@pytest.mark.django_db
def test_follow_user_handles_race_condition(
    user_a: User,
    user_b: User,
) -> None:
    """Duplicate/race condition creation in services raises ConflictException."""
    from services.auth_user_service.apps.accounts.services import follow_user_profile
    from shared.exceptions.base import ConflictException

    # First follow succeeds
    rel = follow_user_profile(user_a.profile, user_b.profile)
    assert rel.status == RelationStatusChoices.ACCEPTED

    # Second follow raises ConflictException
    with pytest.raises(ConflictException):
        follow_user_profile(user_a.profile, user_b.profile)

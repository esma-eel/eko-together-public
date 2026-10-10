"""Tests for Forum post pinning and 10-pinned-posts quota enforcement."""

import uuid
from http import HTTPStatus

import pytest
from dmr.test import DMRClient

from services.forum_service.apps.forums.models import Forum, ForumPinnedPost


@pytest.mark.django_db
def test_pin_post_and_quota_enforcement(
    client: DMRClient,
    sample_forum: Forum,
    admin_headers: dict[str, str],
    member_headers: dict[str, str],
) -> None:
    """Validate pinning posts enforces maximum 10 pinned posts per forum."""
    post_id = uuid.uuid4()

    # Member attempt fails (403)
    resp_member = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{post_id}/pin/",
        data={"is_pinned": True, "pin_order": 1},
        **member_headers,
    )
    assert resp_member.status_code == HTTPStatus.FORBIDDEN

    # Admin pins 1st post
    resp_admin = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{post_id}/pin/",
        data={"is_pinned": True, "pin_order": 1},
        **admin_headers,
    )
    assert resp_admin.status_code == HTTPStatus.OK
    assert resp_admin.json()["is_pinned"] is True
    assert resp_admin.json()["active_pins_count"] == 1

    # Pin 9 more posts (total 10)
    for i in range(2, 11):
        p_id = uuid.uuid4()
        r = client.patch(
            f"/api/v1/forums/{sample_forum.slug}/posts/{p_id}/pin/",
            data={"is_pinned": True, "pin_order": i},
            **admin_headers,
        )
        assert r.status_code == HTTPStatus.OK
        assert r.json()["active_pins_count"] == i

    assert ForumPinnedPost.objects.filter(forum=sample_forum, is_pinned=True).count() == 10

    # 11th post pin attempt fails quota check (422)
    p_eleven = uuid.uuid4()
    resp_eleven = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{p_eleven}/pin/",
        data={"is_pinned": True, "pin_order": 5},
        **admin_headers,
    )
    assert resp_eleven.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Unpin 1st post
    resp_unpin = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{post_id}/pin/",
        data={"is_pinned": False},
        **admin_headers,
    )
    assert resp_unpin.status_code == HTTPStatus.OK
    assert resp_unpin.json()["is_pinned"] is False
    assert resp_unpin.json()["active_pins_count"] == 9

    # Now 11th post can be pinned
    resp_eleven_retry = client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{p_eleven}/pin/",
        data={"is_pinned": True, "pin_order": 5},
        **admin_headers,
    )
    assert resp_eleven_retry.status_code == HTTPStatus.OK
    assert resp_eleven_retry.json()["active_pins_count"] == 10


@pytest.mark.django_db
def test_list_pinned_posts(
    client: DMRClient,
    sample_forum: Forum,
    admin_headers: dict[str, str],
) -> None:
    """Validate listing active pinned posts ordered by pin_order."""
    post_a = uuid.uuid4()
    post_b = uuid.uuid4()

    client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{post_a}/pin/",
        data={"is_pinned": True, "pin_order": 2},
        **admin_headers,
    )
    client.patch(
        f"/api/v1/forums/{sample_forum.slug}/posts/{post_b}/pin/",
        data={"is_pinned": True, "pin_order": 1},
        **admin_headers,
    )

    response = client.get(f"/api/v1/forums/{sample_forum.slug}/pinned-posts/")
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["count"] == 2
    # Verify ordered by pin_order (order 1 first, then order 2)
    assert data["results"][0]["post_id"] == str(post_b)
    assert data["results"][0]["pin_order"] == 1
    assert data["results"][1]["post_id"] == str(post_a)
    assert data["results"][1]["pin_order"] == 2

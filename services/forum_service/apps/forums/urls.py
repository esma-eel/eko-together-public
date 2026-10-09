"""Routing definitions for Forum Service endpoints.

Uses dmr.routing.Router and dmr.routing.path for high-performance prefix-matched dispatch.
"""

from __future__ import annotations

from dmr.routing import Router, path

from services.forum_service.apps.forums.controllers.forum_controllers import (
    ForumDetailController,
    ForumListCreateController,
)
from services.forum_service.apps.forums.controllers.internal_controllers import (
    ForumInternalPermissionController,
)
from services.forum_service.apps.forums.controllers.member_controllers import (
    ForumJoinController,
    ForumLeaveController,
    ForumMemberDetailController,
    ForumMemberListController,
)
from services.forum_service.apps.forums.controllers.pin_controllers import (
    ForumPinnedPostListController,
    ForumPinPostController,
)

api_router = Router(
    "api/",
    [
        # Forum Discovery and Management
        path("v1/forums/", ForumListCreateController.as_view(), name="forums_list_create"),
        path("v1/forums/<str:slug>/", ForumDetailController.as_view(), name="forums_detail"),
        # Subscriptions and Membership
        path(
            "v1/forums/<str:slug>/members/",
            ForumMemberListController.as_view(),
            name="forums_members_list",
        ),
        path("v1/forums/<str:slug>/join/", ForumJoinController.as_view(), name="forums_join"),
        path("v1/forums/<str:slug>/leave/", ForumLeaveController.as_view(), name="forums_leave"),
        path(
            "v1/forums/<str:slug>/members/<str:user_profile_id>/",
            ForumMemberDetailController.as_view(),
            name="forums_member_detail",
        ),
        # Pinned Posts & Moderation
        path(
            "v1/forums/<str:slug>/posts/<str:post_id>/pin/",
            ForumPinPostController.as_view(),
            name="forums_post_pin",
        ),
        path(
            "v1/forums/<str:slug>/pinned-posts/",
            ForumPinnedPostListController.as_view(),
            name="forums_pinned_posts_list",
        ),
    ],
)

internal_router = Router(
    "internal/",
    [
        path(
            "forums/<str:forum_id>/check-permission/",
            ForumInternalPermissionController.as_view(),
            name="internal_forum_check_permission",
        ),
    ],
)

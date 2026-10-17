"""Routing definitions for Posts module.

Uses dmr.routing.Router and dmr.routing.path for high-performance prefix-matched dispatch.
"""

from __future__ import annotations

from dmr.routing import Router, path

from services.post_comment_service.apps.posts.controllers import (
    PostArchiveController,
    PostDetailController,
    PostListCreateController,
    PostPinController,
)

api_router = Router(
    "api/",
    [
        path("v1/posts/", PostListCreateController.as_view(), name="post-list-create"),
        path("v1/posts/<str:post_id>/", PostDetailController.as_view(), name="post-detail"),
        path(
            "v1/posts/<str:post_id>/archive/",
            PostArchiveController.as_view(),
            name="post-archive",
        ),
        path("v1/posts/<str:post_id>/pin/", PostPinController.as_view(), name="post-pin"),
    ],
)

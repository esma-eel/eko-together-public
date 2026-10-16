"""Routing definitions for Comments module.

Uses dmr.routing.Router and dmr.routing.path for high-performance prefix-matched dispatch.
"""

from __future__ import annotations

from dmr.routing import Router, path

from services.post_comment_service.apps.comments.controllers import (
    CommentArchiveController,
    CommentDetailController,
    CommentListCreateController,
    CommentReplyController,
    CommentVoteController,
)

api_router = Router(
    "api/",
    [
        path(
            "v1/posts/<str:post_id>/comments/",
            CommentListCreateController.as_view(),
            name="comment-list-create",
        ),
        path(
            "v1/comments/<str:comment_id>/replies/",
            CommentReplyController.as_view(),
            name="comment-reply",
        ),
        path(
            "v1/comments/<str:comment_id>/",
            CommentDetailController.as_view(),
            name="comment-detail",
        ),
        path(
            "v1/comments/<str:comment_id>/archive/",
            CommentArchiveController.as_view(),
            name="comment-archive",
        ),
        path(
            "v1/comments/<str:comment_id>/vote/",
            CommentVoteController.as_view(),
            name="comment-vote",
        ),
    ],
)

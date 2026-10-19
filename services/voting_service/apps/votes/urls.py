"""DMR URL Routing for Voting Service."""

from __future__ import annotations

from dmr.routing import Router, path

from services.voting_service.apps.votes.controllers import (
    CommentUserVoteController,
    CommentVoteController,
    PostUserVoteController,
    PostVoteController,
)

api_router = Router(
    "api/",
    [
        # Post Voting Endpoints
        path(
            "v1/posts/<str:post_id>/votes/",
            PostVoteController.as_view(),
            name="post-votes",
        ),
        path(
            "v1/posts/<str:post_id>/votes/me/",
            PostUserVoteController.as_view(),
            name="post-user-vote-me",
        ),
        # Comment Voting Endpoints
        path(
            "v1/comments/<str:comment_id>/votes/",
            CommentVoteController.as_view(),
            name="comment-votes",
        ),
        path(
            "v1/comments/<str:comment_id>/votes/me/",
            CommentUserVoteController.as_view(),
            name="comment-user-vote-me",
        ),
    ],
)

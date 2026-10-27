"""URL and Router configuration for Search Service."""

from __future__ import annotations

from dmr.routing import Router, path

from services.search_service.apps.search.controllers import (
    CommentsSearchController,
    ForumsSearchController,
    MediaSearchController,
    PostsSearchController,
    ProfilesSearchController,
    SuggestController,
    UnifiedSearchController,
)

api_router = Router(
    "api/",
    [
        path(
            "v1/search/",
            UnifiedSearchController.as_view(),
            name="search-unified",
        ),
        path(
            "v1/search/posts/",
            PostsSearchController.as_view(),
            name="search-posts",
        ),
        path(
            "v1/search/forums/",
            ForumsSearchController.as_view(),
            name="search-forums",
        ),
        path(
            "v1/search/comments/",
            CommentsSearchController.as_view(),
            name="search-comments",
        ),
        path(
            "v1/search/media/",
            MediaSearchController.as_view(),
            name="search-media",
        ),
        path(
            "v1/search/profiles/",
            ProfilesSearchController.as_view(),
            name="search-profiles",
        ),
        path(
            "v1/search/suggest/",
            SuggestController.as_view(),
            name="search-suggest",
        ),
    ],
)

"""DMR Controllers for Search Service endpoints."""

from __future__ import annotations

from uuid import UUID

from django.conf import settings
from dmr import Controller
from dmr.components import Query
from dmr.plugins.msgspec import MsgspecSerializer

from services.search_service.apps.search.schemas import (
    CommentsSearchQuery,
    CommentsSearchResponse,
    ForumsSearchQuery,
    ForumsSearchResponse,
    MediaSearchQuery,
    MediaSearchResponse,
    PostsSearchQuery,
    PostsSearchResponse,
    ProfilesSearchQuery,
    ProfilesSearchResponse,
    SuggestQuery,
    SuggestResponse,
    UnifiedSearchQuery,
    UnifiedSearchResponse,
)
from services.search_service.apps.search.services import (
    execute_comments_search,
    execute_forums_search,
    execute_media_search,
    execute_posts_search,
    execute_profiles_search,
    execute_suggestions,
    execute_unified_search,
)
from shared.jwt.tokens import load_public_key, verify_and_decode_token


class BaseSearchController(Controller[MsgspecSerializer]):
    """Base search controller providing typed claims accessor for public & authenticated users."""

    @property
    def viewer_profile_id(self) -> UUID | None:
        """Extract viewer profile_id from JWT claims if Bearer token is provided."""
        auth_header = self.request.headers.get("Authorization") or self.request.META.get(
            "HTTP_AUTHORIZATION"
        )
        if auth_header:
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                try:
                    public_key = load_public_key(settings.JWT_PUBLIC_KEY_PATH)
                    claims = verify_and_decode_token(
                        token=parts[1],
                        public_key_pem=public_key,
                        expected_token_type="access",
                    )
                    return claims.profile_id
                except Exception:
                    pass
        return None


class UnifiedSearchController(BaseSearchController):
    """GET /api/v1/search/ - Unified Multi-Entity Search."""

    def get(self, parsed_query: Query[UnifiedSearchQuery]) -> UnifiedSearchResponse:
        return execute_unified_search(
            query=parsed_query,
            viewer_profile_id=self.viewer_profile_id,
        )


class PostsSearchController(BaseSearchController):
    """GET /api/v1/search/posts/ - Dedicated post search with filters & highlighting."""

    def get(self, parsed_query: Query[PostsSearchQuery]) -> PostsSearchResponse:
        return execute_posts_search(
            query=parsed_query,
            viewer_profile_id=self.viewer_profile_id,
        )


class ForumsSearchController(BaseSearchController):
    """GET /api/v1/search/forums/ - Forum and community search."""

    def get(self, parsed_query: Query[ForumsSearchQuery]) -> ForumsSearchResponse:
        return execute_forums_search(query=parsed_query)


class CommentsSearchController(BaseSearchController):
    """GET /api/v1/search/comments/ - Discussion comments and replies search."""

    def get(self, parsed_query: Query[CommentsSearchQuery]) -> CommentsSearchResponse:
        return execute_comments_search(query=parsed_query)


class MediaSearchController(BaseSearchController):
    """GET /api/v1/search/media/ - Post media attachments search."""

    def get(self, parsed_query: Query[MediaSearchQuery]) -> MediaSearchResponse:
        return execute_media_search(query=parsed_query)


class ProfilesSearchController(BaseSearchController):
    """GET /api/v1/search/profiles/ - Public user profiles search."""

    def get(self, parsed_query: Query[ProfilesSearchQuery]) -> ProfilesSearchResponse:
        return execute_profiles_search(
            query=parsed_query,
            viewer_profile_id=self.viewer_profile_id,
        )


class SuggestController(BaseSearchController):
    """GET /api/v1/search/suggest/ - Fast prefix autocomplete for search bar."""

    def get(self, parsed_query: Query[SuggestQuery]) -> SuggestResponse:
        return execute_suggestions(query=parsed_query)

"""Typed request and response schemas (DTOs) for Search Service."""

from __future__ import annotations

import msgspec

# ============================================================================
# Query Parameter Schemas
# ============================================================================


class UnifiedSearchQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/."""

    q: str
    types: str = "profiles,forums,posts,comments,media"
    limit: int = 5


class PostsSearchQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/posts/."""

    q: str | None = None
    tags: str | None = None
    forum_id: str | None = None
    author_id: str | None = None
    has_image: bool | None = None
    sort_by: str = "relevance"  # relevance, latest, top
    timeframe: str = "all"  # all, day, week, month, year
    page: int = 1
    page_size: int = 20


class ForumsSearchQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/forums/."""

    q: str
    post_permission: str | None = None  # ALL_MEMBERS, APPROVED_ONLY, ADMINS_ONLY
    is_locked: bool | None = None
    sort_by: str = "relevance"  # relevance, members_count, created_at
    page: int = 1
    page_size: int = 20


class CommentsSearchQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/comments/."""

    q: str
    post_id: str | None = None
    forum_id: str | None = None
    author_id: str | None = None
    sort_by: str = "relevance"  # relevance, latest, top
    page: int = 1
    page_size: int = 20


class MediaSearchQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/media/."""

    q: str | None = None
    forum_id: str | None = None
    author_id: str | None = None
    sort_by: str = "latest"  # latest, relevance, popularity
    page: int = 1
    page_size: int = 20


class ProfilesSearchQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/profiles/."""

    q: str
    page: int = 1
    page_size: int = 20


class SuggestQuery(msgspec.Struct, kw_only=True):
    """Query parameters for GET /api/v1/search/suggest/."""

    q: str
    limit: int = 6


# ============================================================================
# Response Nested DTOs
# ============================================================================


class PaginationMeta(msgspec.Struct, kw_only=True):
    """Pagination metadata."""

    page: int
    page_size: int
    total_count: int
    total_pages: int


class AuthorRef(msgspec.Struct, kw_only=True):
    """Lightweight author representation."""

    id: str
    display_name: str


class ForumRef(msgspec.Struct, kw_only=True):
    """Lightweight forum representation."""

    id: str
    title: str
    slug: str


class TagRef(msgspec.Struct, kw_only=True):
    """Tag entity representation."""

    id: int | None = None
    name: str
    slug: str


class SearchProfileItem(msgspec.Struct, kw_only=True):
    """Profile item in search responses."""

    id: str
    username: str
    display_name: str
    avatar: str | None = None
    bio: str | None = None
    is_private: bool = False
    relation_status: str = "NONE"


class SearchForumItem(msgspec.Struct, kw_only=True):
    """Forum summary item in unified search."""

    id: str
    title: str
    slug: str
    description: str | None = None
    avatar: str | None = None


class SearchForumDetailItem(msgspec.Struct, kw_only=True):
    """Forum detailed item in forums search."""

    id: str
    title: str
    slug: str
    description: str | None = None
    avatar: str | None = None
    cover_image: str | None = None
    require_approval_to_join: bool = False
    owner: AuthorRef | None = None
    members_count: int = 0
    created_at: str | None = None


class SearchPostSummaryItem(msgspec.Struct, kw_only=True):
    """Post summary item in unified search."""

    id: str
    title: str
    snippet: str
    image: str | None = None
    popularity_score: int = 0
    author: AuthorRef
    forum: ForumRef | None = None
    created_at: str


class SearchPostDetailItem(msgspec.Struct, kw_only=True):
    """Post detailed item in post search."""

    id: str
    title: str
    snippet: str
    image: str | None = None
    author: AuthorRef
    forum: ForumRef | None = None
    tags: list[TagRef] = msgspec.field(default_factory=list)
    is_pinned: bool = False
    popularity_score: int = 0
    upvotes_count: int = 0
    downvotes_count: int = 0
    created_at: str


class SearchCommentItem(msgspec.Struct, kw_only=True):
    """Comment item in comment and unified search."""

    id: str
    post_id: str
    post_title: str | None = None
    snippet: str
    depth: int = 0
    parent_id: str | None = None
    author: AuthorRef
    popularity_score: int = 0
    created_at: str


class PostMediaRef(msgspec.Struct, kw_only=True):
    """Post reference embedded inside media search."""

    id: str
    title: str
    forum_slug: str | None = None


class SearchMediaItem(msgspec.Struct, kw_only=True):
    """Media item with image URL and post metadata."""

    media_url: str
    post: PostMediaRef
    author: AuthorRef
    created_at: str


# ============================================================================
# API Response Root Schemas
# ============================================================================


class UnifiedSearchResults(msgspec.Struct, kw_only=True):
    """Grouped results across entity types."""

    profiles: list[SearchProfileItem] = msgspec.field(default_factory=list)
    forums: list[SearchForumItem] = msgspec.field(default_factory=list)
    posts: list[SearchPostSummaryItem] = msgspec.field(default_factory=list)
    comments: list[SearchCommentItem] = msgspec.field(default_factory=list)
    media: list[SearchMediaItem] = msgspec.field(default_factory=list)


class UnifiedSearchResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/ response schema."""

    query: str
    results: UnifiedSearchResults


class PostsSearchResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/posts/ response schema."""

    meta: PaginationMeta
    results: list[SearchPostDetailItem]


class ForumsSearchResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/forums/ response schema."""

    meta: PaginationMeta
    results: list[SearchForumDetailItem]


class CommentsSearchResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/comments/ response schema."""

    meta: PaginationMeta
    results: list[SearchCommentItem]


class MediaSearchResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/media/ response schema."""

    meta: PaginationMeta
    results: list[SearchMediaItem]


class ProfilesSearchResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/profiles/ response schema."""

    meta: PaginationMeta
    results: list[SearchProfileItem]


class SuggestionItem(msgspec.Struct, kw_only=True):
    """Individual autocomplete suggestion."""

    type: str  # tag, forum, profile, post
    text: str
    url: str


class SuggestResponse(msgspec.Struct, kw_only=True):
    """GET /api/v1/search/suggest/ response schema."""

    suggestions: list[SuggestionItem]

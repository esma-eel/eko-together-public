"""Domain search business logic, query builders, and Elasticsearch execution."""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from elasticsearch import Elasticsearch

from services.search_service.apps.search.client import get_elasticsearch_client
from services.search_service.apps.search.indices import (
    INDEX_COMMENTS,
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
)
from services.search_service.apps.search.schemas import (
    AuthorRef,
    CommentsSearchQuery,
    CommentsSearchResponse,
    ForumRef,
    ForumsSearchQuery,
    ForumsSearchResponse,
    MediaSearchQuery,
    MediaSearchResponse,
    PaginationMeta,
    PostMediaRef,
    PostsSearchQuery,
    PostsSearchResponse,
    ProfilesSearchQuery,
    ProfilesSearchResponse,
    SearchCommentItem,
    SearchForumDetailItem,
    SearchForumItem,
    SearchMediaItem,
    SearchPostDetailItem,
    SearchPostSummaryItem,
    SearchProfileItem,
    SuggestionItem,
    SuggestQuery,
    SuggestResponse,
    TagRef,
    UnifiedSearchQuery,
    UnifiedSearchResponse,
    UnifiedSearchResults,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _calc_pagination(page: int, page_size: int, total_count: int) -> PaginationMeta:
    """Calculate pagination metadata."""
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 1
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
    )


def _extract_snippet(hit: dict[str, Any], default_text: str = "") -> str:
    """Extract highlighted snippet or truncate default text."""
    highlight = hit.get("highlight", {})
    if "body" in highlight and highlight["body"]:
        return " ... ".join(highlight["body"])
    if "title" in highlight and highlight["title"]:
        return " ... ".join(highlight["title"])
    if len(default_text) > 160:
        return default_text[:160] + "..."
    return default_text


# ============================================================================
# 1. Unified Multi-Entity Search
# ============================================================================


def execute_unified_search(
    query: UnifiedSearchQuery,
    viewer_profile_id: UUID | None = None,
    client: Elasticsearch | None = None,
) -> UnifiedSearchResponse:
    """Execute unified search across profiles, forums, posts, comments, and media."""
    es = client or get_elasticsearch_client()
    raw_types = [t.strip().lower() for t in query.types.split(",") if t.strip()]
    allowed_types = (
        set(raw_types) if raw_types else {"profiles", "forums", "posts", "comments", "media"}
    )
    limit = max(1, min(query.limit, 20))

    profiles_res: list[SearchProfileItem] = []
    forums_res: list[SearchForumItem] = []
    posts_res: list[SearchPostSummaryItem] = []
    comments_res: list[SearchCommentItem] = []
    media_res: list[SearchMediaItem] = []

    # Profiles
    if "profiles" in allowed_types:
        try:
            profile_query: dict[str, Any] = {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query.q,
                                "fields": ["username^3", "display_name^2", "bio"],
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": [],
                }
            }
            res = es.search(index=INDEX_PROFILES, query=profile_query, size=limit)
            for hit in res["hits"]["hits"]:
                src = hit["_source"]
                # Privacy filter: hide private profiles unless requesting user is the owner
                if src.get("is_private") and str(viewer_profile_id) != str(src.get("id")):
                    continue
                profiles_res.append(
                    SearchProfileItem(
                        id=str(src.get("id", "")),
                        username=src.get("username", ""),
                        display_name=src.get("display_name", ""),
                        avatar=src.get("avatar"),
                        bio=src.get("bio"),
                        is_private=bool(src.get("is_private", False)),
                        relation_status="OWNER"
                        if str(viewer_profile_id) == str(src.get("id"))
                        else "NONE",
                    )
                )
        except Exception as exc:
            logger.warning("Unified search failed for profiles: %s", exc)

    # Forums
    if "forums" in allowed_types:
        try:
            forum_query = {
                "multi_match": {
                    "query": query.q,
                    "fields": ["title^3", "slug^2", "description"],
                    "fuzziness": "AUTO",
                }
            }
            res = es.search(index=INDEX_FORUMS, query=forum_query, size=limit)
            for hit in res["hits"]["hits"]:
                src = hit["_source"]
                forums_res.append(
                    SearchForumItem(
                        id=str(src.get("id", "")),
                        title=src.get("title", ""),
                        slug=src.get("slug", ""),
                        description=src.get("description"),
                        avatar=src.get("avatar"),
                    )
                )
        except Exception as exc:
            logger.warning("Unified search failed for forums: %s", exc)

    # Posts
    if "posts" in allowed_types:
        try:
            post_query: dict[str, Any] = {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query.q,
                                "fields": ["title^3", "body", "tags^2"],
                                "fuzziness": "AUTO",
                            }
                        }
                    ],
                    "filter": [{"term": {"is_deleted": False}}],
                }
            }
            # Privacy: default to PUBLIC or viewer's own posts
            if viewer_profile_id:
                post_query["bool"]["filter"].append(
                    {
                        "bool": {
                            "should": [
                                {"term": {"visibility": "PUBLIC"}},
                                {"term": {"author_id": str(viewer_profile_id)}},
                            ],
                            "minimum_should_match": 1,
                        }
                    }
                )
            else:
                post_query["bool"]["filter"].append({"term": {"visibility": "PUBLIC"}})

            res = es.search(
                index=INDEX_POSTS,
                query=post_query,
                size=limit,
                highlight={"fields": {"body": {}, "title": {}}},
            )
            for hit in res["hits"]["hits"]:
                src = hit["_source"]
                snippet = _extract_snippet(hit, src.get("body", ""))
                forum_obj = None
                if src.get("forum_id"):
                    forum_obj = ForumRef(
                        id=str(src["forum_id"]),
                        title=src.get("forum_title", "General"),
                        slug=src.get("forum_slug", "general"),
                    )
                posts_res.append(
                    SearchPostSummaryItem(
                        id=str(src.get("id", "")),
                        title=src.get("title", ""),
                        snippet=snippet,
                        image=src.get("image"),
                        popularity_score=int(src.get("popularity_score", 0)),
                        author=AuthorRef(
                            id=str(src.get("author_id", "")),
                            display_name=src.get("author_display_name", "Author"),
                        ),
                        forum=forum_obj,
                        created_at=str(src.get("created_at", "")),
                    )
                )
        except Exception as exc:
            logger.warning("Unified search failed for posts: %s", exc)

    # Comments
    if "comments" in allowed_types:
        try:
            comment_query = {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "body": {
                                    "query": query.q,
                                    "fuzziness": "AUTO",
                                }
                            }
                        }
                    ],
                    "filter": [{"term": {"is_deleted": False}}],
                }
            }
            res = es.search(
                index=INDEX_COMMENTS,
                query=comment_query,
                size=limit,
                highlight={"fields": {"body": {}}},
            )
            for hit in res["hits"]["hits"]:
                src = hit["_source"]
                snippet = _extract_snippet(hit, src.get("body", ""))
                comments_res.append(
                    SearchCommentItem(
                        id=str(src.get("id", "")),
                        post_id=str(src.get("post_id", "")),
                        post_title=src.get("post_title"),
                        snippet=snippet,
                        depth=int(src.get("depth", 0)),
                        parent_id=str(src["parent_id"]) if src.get("parent_id") else None,
                        author=AuthorRef(
                            id=str(src.get("author_id", "")),
                            display_name=src.get("author_display_name", "User"),
                        ),
                        popularity_score=int(src.get("popularity_score", 0)),
                        created_at=str(src.get("created_at", "")),
                    )
                )
        except Exception as exc:
            logger.warning("Unified search failed for comments: %s", exc)

    # Media
    if "media" in allowed_types:
        try:
            media_query = {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query.q,
                                "fields": ["title^2", "body", "tags"],
                            }
                        }
                    ],
                    "filter": [
                        {"term": {"is_deleted": False}},
                        {"term": {"has_image": True}},
                        {"term": {"visibility": "PUBLIC"}},
                    ],
                }
            }
            res = es.search(index=INDEX_POSTS, query=media_query, size=limit)
            for hit in res["hits"]["hits"]:
                src = hit["_source"]
                if not src.get("image"):
                    continue
                media_res.append(
                    SearchMediaItem(
                        media_url=src["image"],
                        post=PostMediaRef(
                            id=str(src.get("id", "")),
                            title=src.get("title", ""),
                            forum_slug=src.get("forum_slug"),
                        ),
                        author=AuthorRef(
                            id=str(src.get("author_id", "")),
                            display_name=src.get("author_display_name", "Author"),
                        ),
                        created_at=str(src.get("created_at", "")),
                    )
                )
        except Exception as exc:
            logger.warning("Unified search failed for media: %s", exc)

    return UnifiedSearchResponse(
        query=query.q,
        results=UnifiedSearchResults(
            profiles=profiles_res,
            forums=forums_res,
            posts=posts_res,
            comments=comments_res,
            media=media_res,
        ),
    )


# ============================================================================
# 2. Search Posts
# ============================================================================


def execute_posts_search(
    query: PostsSearchQuery,
    viewer_profile_id: UUID | None = None,
    client: Elasticsearch | None = None,
) -> PostsSearchResponse:
    """Search posts with query keywords, tags, timeframe, forum, author, and sorting."""
    es = client or get_elasticsearch_client()
    page = max(1, query.page)
    page_size = max(1, min(query.page_size, 100))
    from_offset = (page - 1) * page_size

    filters: list[dict[str, Any]] = [{"term": {"is_deleted": False}}]
    must_clauses: list[dict[str, Any]] = []

    # Keyword match
    if query.q and query.q.strip():
        must_clauses.append(
            {
                "multi_match": {
                    "query": query.q.strip(),
                    "fields": ["title^3", "body", "tags^2"],
                    "fuzziness": "AUTO",
                }
            }
        )
    else:
        must_clauses.append({"match_all": {}})

    # Tags filter
    if query.tags:
        tag_list = [t.strip().lower() for t in query.tags.split(",") if t.strip()]
        if tag_list:
            filters.append({"terms": {"tags": tag_list}})

    # Forum filter
    if query.forum_id:
        filters.append({"term": {"forum_id": str(query.forum_id)}})

    # Author filter
    if query.author_id:
        filters.append({"term": {"author_id": str(query.author_id)}})

    # Media filter
    if query.has_image is not None:
        filters.append({"term": {"has_image": query.has_image}})

    # Timeframe filter
    if query.timeframe and query.timeframe != "all":
        now = datetime.now(tz=UTC)
        time_delta_map = {
            "day": timedelta(days=1),
            "week": timedelta(days=7),
            "month": timedelta(days=30),
            "year": timedelta(days=365),
        }
        delta = time_delta_map.get(query.timeframe)
        if delta:
            threshold = (now - delta).isoformat()
            filters.append({"range": {"created_at": {"gte": threshold}}})

    # Visibility / Privacy
    if viewer_profile_id:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"visibility": "PUBLIC"}},
                        {"term": {"author_id": str(viewer_profile_id)}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    else:
        filters.append({"term": {"visibility": "PUBLIC"}})

    # Sorting
    sort_criteria: list[dict[str, Any]]
    if query.sort_by == "latest":
        sort_criteria = [{"created_at": {"order": "desc"}}]
    elif query.sort_by == "top":
        sort_criteria = [{"popularity_score": {"order": "desc"}}, {"created_at": {"order": "desc"}}]
    else:
        sort_criteria = [{"_score": {"order": "desc"}}, {"created_at": {"order": "desc"}}]

    body = {
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filters,
            }
        },
        "sort": sort_criteria,
        "from": from_offset,
        "size": page_size,
        "highlight": {
            "pre_tags": ["<b>"],
            "post_tags": ["</b>"],
            "fields": {"body": {}, "title": {}},
        },
    }

    try:
        res = es.search(index=INDEX_POSTS, **body)
        total_hits = (
            res["hits"]["total"]["value"]
            if isinstance(res["hits"]["total"], dict)
            else res["hits"]["total"]
        )
        results: list[SearchPostDetailItem] = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            snippet = _extract_snippet(hit, src.get("body", ""))
            forum_obj = None
            if src.get("forum_id"):
                forum_obj = ForumRef(
                    id=str(src["forum_id"]),
                    title=src.get("forum_title", "General"),
                    slug=src.get("forum_slug", "general"),
                )
            tags_list = [TagRef(name=t, slug=t) for t in src.get("tags", [])]
            results.append(
                SearchPostDetailItem(
                    id=str(src.get("id", "")),
                    title=src.get("title", ""),
                    snippet=snippet,
                    image=src.get("image"),
                    author=AuthorRef(
                        id=str(src.get("author_id", "")),
                        display_name=src.get("author_display_name", "Author"),
                    ),
                    forum=forum_obj,
                    tags=tags_list,
                    is_pinned=bool(src.get("is_pinned", False)),
                    popularity_score=int(src.get("popularity_score", 0)),
                    upvotes_count=int(src.get("upvotes_count", 0)),
                    downvotes_count=int(src.get("downvotes_count", 0)),
                    created_at=str(src.get("created_at", "")),
                )
            )
        return PostsSearchResponse(
            meta=_calc_pagination(page, page_size, total_hits),
            results=results,
        )
    except Exception as exc:
        logger.error("Error executing posts search: %s", exc)
        return PostsSearchResponse(
            meta=_calc_pagination(page, page_size, 0),
            results=[],
        )


# ============================================================================
# 3. Search Forums
# ============================================================================


def execute_forums_search(
    query: ForumsSearchQuery,
    client: Elasticsearch | None = None,
) -> ForumsSearchResponse:
    """Search forums by title, slug, and description with filters."""
    es = client or get_elasticsearch_client()
    page = max(1, query.page)
    page_size = max(1, min(query.page_size, 100))
    from_offset = (page - 1) * page_size

    filters: list[dict[str, Any]] = []
    if query.post_permission:
        filters.append({"term": {"post_permission": query.post_permission}})
    if query.is_locked is not None:
        filters.append({"term": {"is_comments_locked": query.is_locked}})

    must_clause = {
        "multi_match": {
            "query": query.q,
            "fields": ["title^3", "slug^2", "description"],
            "fuzziness": "AUTO",
        }
    }

    sort_criteria: list[dict[str, Any]]
    if query.sort_by == "members_count":
        sort_criteria = [{"members_count": {"order": "desc"}}]
    elif query.sort_by == "created_at":
        sort_criteria = [{"created_at": {"order": "desc"}}]
    else:
        sort_criteria = [{"_score": {"order": "desc"}}, {"members_count": {"order": "desc"}}]

    body = {
        "query": {
            "bool": {
                "must": [must_clause],
                "filter": filters,
            }
        },
        "sort": sort_criteria,
        "from": from_offset,
        "size": page_size,
    }

    try:
        res = es.search(index=INDEX_FORUMS, **body)
        total_hits = (
            res["hits"]["total"]["value"]
            if isinstance(res["hits"]["total"], dict)
            else res["hits"]["total"]
        )
        results: list[SearchForumDetailItem] = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            owner_obj = None
            if src.get("owner_id"):
                owner_obj = AuthorRef(
                    id=str(src["owner_id"]),
                    display_name=src.get("owner_display_name", "Forum Owner"),
                )
            results.append(
                SearchForumDetailItem(
                    id=str(src.get("id", "")),
                    title=src.get("title", ""),
                    slug=src.get("slug", ""),
                    description=src.get("description"),
                    avatar=src.get("avatar"),
                    cover_image=src.get("cover_image"),
                    require_approval_to_join=bool(src.get("require_approval_to_join", False)),
                    owner=owner_obj,
                    members_count=int(src.get("members_count", 0)),
                    created_at=str(src.get("created_at", "")),
                )
            )
        return ForumsSearchResponse(
            meta=_calc_pagination(page, page_size, total_hits),
            results=results,
        )
    except Exception as exc:
        logger.error("Error executing forums search: %s", exc)
        return ForumsSearchResponse(
            meta=_calc_pagination(page, page_size, 0),
            results=[],
        )


# ============================================================================
# 4. Search Comments
# ============================================================================


def execute_comments_search(
    query: CommentsSearchQuery,
    client: Elasticsearch | None = None,
) -> CommentsSearchResponse:
    """Search comments matching keywords in comment body."""
    es = client or get_elasticsearch_client()
    page = max(1, query.page)
    page_size = max(1, min(query.page_size, 100))
    from_offset = (page - 1) * page_size

    filters: list[dict[str, Any]] = [{"term": {"is_deleted": False}}]
    if query.post_id:
        filters.append({"term": {"post_id": str(query.post_id)}})
    if query.forum_id:
        filters.append({"term": {"forum_id": str(query.forum_id)}})
    if query.author_id:
        filters.append({"term": {"author_id": str(query.author_id)}})

    must_clause = {
        "match": {
            "body": {
                "query": query.q,
                "fuzziness": "AUTO",
            }
        }
    }

    sort_criteria: list[dict[str, Any]]
    if query.sort_by == "latest":
        sort_criteria = [{"created_at": {"order": "desc"}}]
    elif query.sort_by == "top":
        sort_criteria = [{"popularity_score": {"order": "desc"}}]
    else:
        sort_criteria = [{"_score": {"order": "desc"}}, {"popularity_score": {"order": "desc"}}]

    body = {
        "query": {
            "bool": {
                "must": [must_clause],
                "filter": filters,
            }
        },
        "sort": sort_criteria,
        "from": from_offset,
        "size": page_size,
        "highlight": {
            "pre_tags": ["<b>"],
            "post_tags": ["</b>"],
            "fields": {"body": {}},
        },
    }

    try:
        res = es.search(index=INDEX_COMMENTS, **body)
        total_hits = (
            res["hits"]["total"]["value"]
            if isinstance(res["hits"]["total"], dict)
            else res["hits"]["total"]
        )
        results: list[SearchCommentItem] = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            snippet = _extract_snippet(hit, src.get("body", ""))
            results.append(
                SearchCommentItem(
                    id=str(src.get("id", "")),
                    post_id=str(src.get("post_id", "")),
                    post_title=src.get("post_title"),
                    snippet=snippet,
                    depth=int(src.get("depth", 0)),
                    parent_id=str(src["parent_id"]) if src.get("parent_id") else None,
                    author=AuthorRef(
                        id=str(src.get("author_id", "")),
                        display_name=src.get("author_display_name", "Author"),
                    ),
                    popularity_score=int(src.get("popularity_score", 0)),
                    created_at=str(src.get("created_at", "")),
                )
            )
        return CommentsSearchResponse(
            meta=_calc_pagination(page, page_size, total_hits),
            results=results,
        )
    except Exception as exc:
        logger.error("Error executing comments search: %s", exc)
        return CommentsSearchResponse(
            meta=_calc_pagination(page, page_size, 0),
            results=[],
        )


# ============================================================================
# 5. Search Media
# ============================================================================


def execute_media_search(
    query: MediaSearchQuery,
    client: Elasticsearch | None = None,
) -> MediaSearchResponse:
    """Search post media images matching metadata keywords."""
    es = client or get_elasticsearch_client()
    page = max(1, query.page)
    page_size = max(1, min(query.page_size, 100))
    from_offset = (page - 1) * page_size

    filters: list[dict[str, Any]] = [
        {"term": {"is_deleted": False}},
        {"term": {"has_image": True}},
        {"term": {"visibility": "PUBLIC"}},
    ]
    if query.forum_id:
        filters.append({"term": {"forum_id": str(query.forum_id)}})
    if query.author_id:
        filters.append({"term": {"author_id": str(query.author_id)}})

    must_clause = (
        {
            "multi_match": {
                "query": query.q.strip(),
                "fields": ["title^2", "body", "tags"],
            }
        }
        if query.q and query.q.strip()
        else {"match_all": {}}
    )

    sort_criteria: list[dict[str, Any]]
    if query.sort_by == "popularity":
        sort_criteria = [{"popularity_score": {"order": "desc"}}]
    elif query.sort_by == "relevance":
        sort_criteria = [{"_score": {"order": "desc"}}, {"created_at": {"order": "desc"}}]
    else:
        sort_criteria = [{"created_at": {"order": "desc"}}]

    body = {
        "query": {
            "bool": {
                "must": [must_clause],
                "filter": filters,
            }
        },
        "sort": sort_criteria,
        "from": from_offset,
        "size": page_size,
    }

    try:
        res = es.search(index=INDEX_POSTS, **body)
        total_hits = (
            res["hits"]["total"]["value"]
            if isinstance(res["hits"]["total"], dict)
            else res["hits"]["total"]
        )
        results: list[SearchMediaItem] = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            if not src.get("image"):
                continue
            results.append(
                SearchMediaItem(
                    media_url=src["image"],
                    post=PostMediaRef(
                        id=str(src.get("id", "")),
                        title=src.get("title", ""),
                        forum_slug=src.get("forum_slug"),
                    ),
                    author=AuthorRef(
                        id=str(src.get("author_id", "")),
                        display_name=src.get("author_display_name", "Author"),
                    ),
                    created_at=str(src.get("created_at", "")),
                )
            )
        return MediaSearchResponse(
            meta=_calc_pagination(page, page_size, total_hits),
            results=results,
        )
    except Exception as exc:
        logger.error("Error executing media search: %s", exc)
        return MediaSearchResponse(
            meta=_calc_pagination(page, page_size, 0),
            results=[],
        )


# ============================================================================
# 6. Search Profiles
# ============================================================================


def execute_profiles_search(
    query: ProfilesSearchQuery,
    viewer_profile_id: UUID | None = None,
    client: Elasticsearch | None = None,
) -> ProfilesSearchResponse:
    """Search public and accessible user profiles."""
    es = client or get_elasticsearch_client()
    page = max(1, query.page)
    page_size = max(1, min(query.page_size, 100))
    from_offset = (page - 1) * page_size

    must_clause = {
        "multi_match": {
            "query": query.q,
            "fields": ["username^3", "display_name^2", "bio"],
            "fuzziness": "AUTO",
        }
    }

    filters: list[dict[str, Any]] = []
    if viewer_profile_id:
        filters.append(
            {
                "bool": {
                    "should": [
                        {"term": {"is_private": False}},
                        {"term": {"id": str(viewer_profile_id)}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    else:
        filters.append({"term": {"is_private": False}})

    body = {
        "query": {
            "bool": {
                "must": [must_clause],
                "filter": filters,
            }
        },
        "from": from_offset,
        "size": page_size,
    }

    try:
        res = es.search(index=INDEX_PROFILES, **body)
        total_hits = (
            res["hits"]["total"]["value"]
            if isinstance(res["hits"]["total"], dict)
            else res["hits"]["total"]
        )
        results: list[SearchProfileItem] = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            # Check privacy
            is_own_profile = str(viewer_profile_id) == str(src.get("id"))
            if src.get("is_private") and not is_own_profile:
                continue
            results.append(
                SearchProfileItem(
                    id=str(src.get("id", "")),
                    username=src.get("username", ""),
                    display_name=src.get("display_name", ""),
                    avatar=src.get("avatar"),
                    bio=src.get("bio"),
                    is_private=bool(src.get("is_private", False)),
                    relation_status="OWNER" if is_own_profile else "NONE",
                )
            )
        return ProfilesSearchResponse(
            meta=_calc_pagination(page, page_size, total_hits),
            results=results,
        )
    except Exception as exc:
        logger.error("Error executing profiles search: %s", exc)
        return ProfilesSearchResponse(
            meta=_calc_pagination(page, page_size, 0),
            results=[],
        )


# ============================================================================
# 7. Search Suggestions / Autocomplete
# ============================================================================


def execute_suggestions(
    query: SuggestQuery,
    client: Elasticsearch | None = None,
) -> SuggestResponse:
    """Provide fast search-as-you-type autocomplete suggestions.

    Queries across tags, forums, profiles, and post titles.
    """
    es = client or get_elasticsearch_client()
    limit = max(1, min(query.limit, 15))
    q_str = query.q.strip()
    if len(q_str) < 2:
        return SuggestResponse(suggestions=[])

    suggestions: list[SuggestionItem] = []

    # 1. Search Forums autocomplete
    try:
        forum_query = {
            "multi_match": {
                "query": q_str,
                "type": "bool_prefix",
                "fields": [
                    "title.suggest",
                    "title.suggest._2gram",
                    "title.suggest._3gram",
                    "slug.text",
                ],
            }
        }
        res = es.search(index=INDEX_FORUMS, query=forum_query, size=limit)
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            suggestions.append(
                SuggestionItem(
                    type="forum",
                    text=src.get("title", ""),
                    url=f"/f/{src.get('slug', '')}",
                )
            )
            if len(suggestions) >= limit:
                return SuggestResponse(suggestions=suggestions)
    except Exception as exc:
        logger.debug("Autocomplete forums failed: %s", exc)

    # 2. Search Profiles autocomplete
    try:
        profile_query = {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q_str,
                            "type": "bool_prefix",
                            "fields": [
                                "username.suggest",
                                "username.suggest._2gram",
                                "username.suggest._3gram",
                                "display_name.suggest",
                            ],
                        }
                    }
                ],
                "filter": [{"term": {"is_private": False}}],
            }
        }
        res = es.search(index=INDEX_PROFILES, query=profile_query, size=limit)
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            suggestions.append(
                SuggestionItem(
                    type="profile",
                    text=src.get("username", ""),
                    url=f"/u/{src.get('username', '')}",
                )
            )
            if len(suggestions) >= limit:
                return SuggestResponse(suggestions=suggestions)
    except Exception as exc:
        logger.debug("Autocomplete profiles failed: %s", exc)

    # 3. Search Posts autocomplete
    try:
        post_query = {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": q_str,
                            "type": "bool_prefix",
                            "fields": [
                                "title.suggest",
                                "title.suggest._2gram",
                                "title.suggest._3gram",
                            ],
                        }
                    }
                ],
                "filter": [
                    {"term": {"is_deleted": False}},
                    {"term": {"visibility": "PUBLIC"}},
                ],
            }
        }
        res = es.search(index=INDEX_POSTS, query=post_query, size=limit)
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            suggestions.append(
                SuggestionItem(
                    type="post",
                    text=src.get("title", ""),
                    url=f"/posts/{src.get('id', '')}",
                )
            )
            if len(suggestions) >= limit:
                return SuggestResponse(suggestions=suggestions)
    except Exception as exc:
        logger.debug("Autocomplete posts failed: %s", exc)

    return SuggestResponse(suggestions=suggestions[:limit])

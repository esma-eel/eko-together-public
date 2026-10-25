"""Typed DTO Schemas for Feed and Ranking Service.

Built using high-performance msgspec.Struct for sub-millisecond serialization.
Conforms to contracts in docs/architecture/02.api defenitions/07.feed/12.feed.md.
"""

from __future__ import annotations

import msgspec

# ============================================================================
# Query Schemas
# ============================================================================


class ExploreFeedQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for global discovery / popular feed."""

    sort: str = "popular"  # popular | recent
    timeframe: str = "day"  # day | week | month | all
    source: str = "all"  # all | forums_only | profiles_only
    cursor: str | None = None
    limit: int = 20


class ForumsFeedQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for user joined-forums feed."""

    sort: str = "recent"  # recent | popular
    timeframe: str = "day"  # day | week | month | all
    cursor: str | None = None
    limit: int = 20


class FollowingFeedQuerySchema(msgspec.Struct, kw_only=True):
    """Query parameters for user personalized following feed."""

    sort: str = "recent"  # recent | popular
    cursor: str | None = None
    limit: int = 20


# ============================================================================
# Nested Entity Schemas
# ============================================================================


class AuthorFeedSchema(msgspec.Struct, kw_only=True):
    """Denormalized author snapshot embedded in feed responses."""

    id: str
    display_name: str
    avatar: str | None = None


class ForumFeedSchema(msgspec.Struct, kw_only=True):
    """Denormalized forum snapshot embedded in feed responses."""

    id: str
    title: str
    slug: str


class FeedMetricsSchema(msgspec.Struct, kw_only=True):
    """Aggregate engagement metrics."""

    upvotes_count: int = 0
    downvotes_count: int = 0
    popularity_score: int = 0
    comments_count: int = 0


class FeedUserContextSchema(msgspec.Struct, kw_only=True):
    """Contextual interaction state for the requesting user."""

    voted: int = 0  # +1 for upvote, -1 for downvote, 0 for none


class FeedItemSchema(msgspec.Struct, kw_only=True):
    """Individual feed card representation."""

    id: str
    title: str
    body_preview: str
    image: str | None = None
    author: AuthorFeedSchema
    forum: ForumFeedSchema | None = None
    metrics: FeedMetricsSchema
    user_context: FeedUserContextSchema
    created_at: str


class FeedPaginationSchema(msgspec.Struct, kw_only=True):
    """Keyset / cursor pagination metadata."""

    next_cursor: str | None = None
    has_more: bool = False


# ============================================================================
# Response Schemas
# ============================================================================


class FeedResponseSchema(msgspec.Struct, kw_only=True):
    """Envelope response containing list of feed items and pagination."""

    data: list[FeedItemSchema]
    pagination: FeedPaginationSchema


class HealthResponseSchema(msgspec.Struct, kw_only=True):
    """System health check status for Feed Service."""

    status: str
    service: str
    redis: str
    voting_db: str
    mongo: str
    timestamp: str

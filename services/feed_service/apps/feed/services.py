"""Business logic and CQRS Read Model services for Feed Service.

Implements:
1. Periodic 24-Hour Sliding Window Calculation (CQRS Command Path) using
   PostgreSQL Voting DB aggregation, MongoDB post filtering, and Redis Sorted Sets atomic swap.
2. High-speed, sub-10ms feed retrieval with Redis ZSETs and Keyset Pagination (CQRS Query Path).
3. Contextual feeds: Global Explore, Joined Forums, and Personalized Following.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from django.conf import settings
from django.db import connections
from pymongo import MongoClient

from services.feed_service.apps.feed.schemas import (
    AuthorFeedSchema,
    ExploreFeedQuerySchema,
    FeedItemSchema,
    FeedMetricsSchema,
    FeedPaginationSchema,
    FeedResponseSchema,
    FeedUserContextSchema,
    FollowingFeedQuerySchema,
    ForumFeedSchema,
    ForumsFeedQuerySchema,
)

logger = logging.getLogger(__name__)

# Redis Sorted Set Keys
REDIS_KEY_POPULAR_24H_GLOBAL = "feed:popular:24h:global"
REDIS_KEY_POPULAR_24H_TEMP = "feed:popular:24h:temp"


# ============================================================================
# Client & Connection Helpers
# ============================================================================


def get_redis_client() -> redis.Redis:
    """Create and return a configured Redis client instance."""
    return redis.Redis(
        host=getattr(settings, "REDIS_HOST", "127.0.0.1"),
        port=getattr(settings, "REDIS_PORT", 6379),
        db=getattr(settings, "REDIS_DB", 0),
        decode_responses=True,
    )


def get_mongo_posts_collection():
    """Return MongoDB collection for posts read queries."""
    mongo_uri = getattr(settings, "MONGO_URI", "mongodb://127.0.0.1:27017/")
    if getattr(settings, "USE_MONGOMOCK", False) or mongo_uri.startswith("mongomock://"):
        try:
            from services.post_comment_service.db import get_posts_collection
            return get_posts_collection()
        except ImportError:
            import mongomock
            client = mongomock.MongoClient(uuidRepresentation="standard")
    else:
        client = MongoClient(mongo_uri)
    db = client[getattr(settings, "MONGO_DATABASE", "posts_comments_db")]
    return db["posts"]



# ============================================================================
# Keyset Pagination Helpers
# ============================================================================


def encode_cursor(cursor_data: dict[str, Any]) -> str:
    """Encode pagination metadata dictionary to opaque base64 cursor."""
    raw = json.dumps(cursor_data, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor_str: str | None) -> dict[str, Any] | None:
    """Decode base64 cursor string into dictionary."""
    if not cursor_str:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to decode cursor: %s", cursor_str)
        return None


# ============================================================================
# CQRS Command Path: 24-Hour Sliding Window Calculation
# ============================================================================


def compute_24h_sliding_window(
    redis_client: redis.Redis | None = None,
    voting_db_alias: str = "voting_db",
) -> dict[str, Any]:
    """Execute batch computation of 24-hour sliding window popular feed.

    1. Executes aggregate query on Voting DB:
       SELECT target_id, SUM(value) AS net_score
       WHERE created_at >= NOW() - INTERVAL '24 hours' AND target_type = 'POST'
       GROUP BY target_id HAVING SUM(value) > 0;
    2. Validates post existence and non-deleted status in MongoDB;
    3. Pipeline writes scores to temporary Redis key: feed:popular:24h:temp;
    4. Performs atomic RENAME to feed:popular:24h:global for zero downtime.
    """
    if redis_client is None:
        redis_client = get_redis_client()

    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(hours=24)

    # 1. Fetch net 24h scores from Voting DB
    scores_by_post: dict[str, float] = {}

    try:
        conn = connections[voting_db_alias]
        with conn.cursor() as cursor:
            vendor = conn.vendor
            if vendor == "sqlite":
                # SQLite syntax for testing (format cutoff matching SQLite datetime representation)
                cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    """
                    SELECT target_id, SUM(value) AS net_score
                    FROM votes
                    WHERE created_at >= %s AND target_type = 'POST'
                    GROUP BY target_id
                    HAVING SUM(value) > 0
                    ORDER BY net_score DESC
                    """,
                    [cutoff_str],
                )
            else:
                # PostgreSQL syntax
                cursor.execute(
                    """
                    SELECT target_id::text, SUM(value) AS net_score
                    FROM votes
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                      AND target_type = 'POST'
                    GROUP BY target_id
                    HAVING SUM(value) > 0
                    ORDER BY net_score DESC
                    """
                )
            rows = cursor.fetchall()
            for target_id, net_score in rows:
                try:
                    norm_id = str(uuid.UUID(str(target_id)))
                except Exception:
                    norm_id = str(target_id)
                scores_by_post[norm_id] = float(net_score)
    except Exception as exc:
        logger.warning("Could not query Voting DB (%s): %s", voting_db_alias, exc)

    # 2. Filter active posts from MongoDB
    post_ids = list(scores_by_post.keys())
    valid_post_ids: set[str] = set()

    if post_ids:
        try:
            posts_col = get_mongo_posts_collection()
            cursor = posts_col.find(
                {
                    "_id": {"$in": post_ids},
                    "is_deleted": False,
                    "is_archived": False,
                },
                {"_id": 1},
            )
            for doc in cursor:
                valid_post_ids.add(str(doc["_id"]))
        except Exception as exc:
            logger.warning("Could not verify posts in MongoDB: %s", exc)
            # If Mongo is temporarily unavailable, retain post IDs
            valid_post_ids = set(post_ids)

    # 3. Write to temporary Redis key and atomic RENAME
    try:
        pipe = redis_client.pipeline()
        pipe.delete(REDIS_KEY_POPULAR_24H_TEMP)

        scored_mapping = {
            pid: score for pid, score in scores_by_post.items() if pid in valid_post_ids
        }

        if scored_mapping:
            pipe.zadd(REDIS_KEY_POPULAR_24H_TEMP, scored_mapping)
            pipe.rename(REDIS_KEY_POPULAR_24H_TEMP, REDIS_KEY_POPULAR_24H_GLOBAL)
            pipe.execute()
        else:
            # If no posts have positive votes in 24h, clear/initialize global key
            pipe.delete(REDIS_KEY_POPULAR_24H_GLOBAL)
            pipe.execute()

        count = len(scored_mapping)
        logger.info("Successfully refreshed popular 24h feed with %d posts.", count)
        return {"status": "success", "posts_ranked": count, "timestamp": now.isoformat()}
    except Exception as exc:
        logger.error("Failed to update Redis 24h feed: %s", exc)
        return {"status": "error", "error": str(exc), "timestamp": now.isoformat()}


# ============================================================================
# Hydration & Enrichment Helpers
# ============================================================================


def hydrate_feed_items(
    post_docs: list[dict[str, Any]],
    current_user_profile_id: str | None = None,
    popularity_scores_override: dict[str, int] | None = None,
) -> list[FeedItemSchema]:
    """Hydrate raw MongoDB documents into typed FeedItemSchema DTOs."""
    user_votes: dict[str, int] = {}

    if current_user_profile_id and post_docs:
        for db_alias in ("voting_db", "default"):
            if db_alias not in connections:
                continue
            try:
                conn = connections[db_alias]
                p_ids = [str(doc["_id"]) for doc in post_docs]
                vendor = conn.vendor
                if vendor == "sqlite":
                    target_col = "target_id"
                    try:
                        user_id_param = uuid.UUID(str(current_user_profile_id)).hex
                    except Exception:
                        user_id_param = str(current_user_profile_id)
                    search_ids = []
                    for pid in p_ids:
                        search_ids.append(pid)
                        try:
                            search_ids.append(uuid.UUID(pid).hex)
                        except Exception:
                            pass
                    search_ids = list(set(search_ids))
                else:
                    target_col = "target_id::text"
                    user_id_param = str(current_user_profile_id)
                    search_ids = p_ids

                with conn.cursor() as cursor:
                    placeholders = ", ".join(["%s"] * len(search_ids))
                    cursor.execute(
                        f"""
                        SELECT {target_col}, value
                        FROM votes
                        WHERE user_profile_id = %s
                          AND target_type = 'POST'
                          AND {target_col} IN ({placeholders})
                        """,
                        [user_id_param, *search_ids],
                    )
                    for t_id, val in cursor.fetchall():
                        try:
                            norm_tid = str(uuid.UUID(str(t_id)))
                        except Exception:
                            norm_tid = str(t_id)
                        user_votes[norm_tid] = int(val)
                if user_votes:
                    break
            except Exception:
                pass

    items: list[FeedItemSchema] = []
    for doc in post_docs:
        pid = str(doc["_id"])
        body = doc.get("body", "")
        preview = (body[:200] + "...") if len(body) > 200 else body

        # Author Snapshot
        author_id = str(doc.get("author_profile_id", ""))
        author = AuthorFeedSchema(
            id=author_id,
            display_name=doc.get("author_display_name", f"User-{author_id[:6]}"),
            avatar=doc.get("author_avatar"),
        )

        # Forum Snapshot
        forum = None
        if doc.get("forum_id"):
            fid = str(doc["forum_id"])
            forum = ForumFeedSchema(
                id=fid,
                title=doc.get("forum_title", f"Forum-{fid[:6]}"),
                slug=doc.get("forum_slug", f"forum-{fid[:6]}"),
            )

        # Engagement Metrics
        pop_score = (
            popularity_scores_override.get(pid, doc.get("popularity_score", 0))
            if popularity_scores_override
            else doc.get("popularity_score", 0)
        )

        metrics = FeedMetricsSchema(
            upvotes_count=doc.get("upvotes_count", 0),
            downvotes_count=doc.get("downvotes_count", 0),
            popularity_score=pop_score,
            comments_count=doc.get("comments_count", 0),
        )

        # User Vote Context
        user_voted = user_votes.get(pid, 0)
        user_context = FeedUserContextSchema(voted=user_voted)

        # Timestamp
        created_val = doc.get("created_at")
        if isinstance(created_val, datetime):
            created_str = created_val.isoformat()
        else:
            created_str = str(created_val or "")

        items.append(
            FeedItemSchema(
                id=pid,
                title=doc.get("title", ""),
                body_preview=preview,
                image=doc.get("image"),
                author=author,
                forum=forum,
                metrics=metrics,
                user_context=user_context,
                created_at=created_str,
            )
        )

    return items


# ============================================================================
# CQRS Query Path: Feed Retrieval
# ============================================================================


def get_explore_feed(
    query: ExploreFeedQuerySchema,
    current_user_profile_id: str | None = None,
    redis_client: redis.Redis | None = None,
) -> FeedResponseSchema:
    """Retrieve global explore feed with sub-10ms Redis ZSET or MongoDB read."""
    limit = max(1, min(query.limit, 50))
    fetch_limit = limit + 1

    if redis_client is None:
        redis_client = get_redis_client()

    posts_col = get_mongo_posts_collection()

    # Route 1: 24h Popular Feed via Redis Sorted Set
    if query.sort == "popular" and query.timeframe == "day":
        cursor_data = decode_cursor(query.cursor)

        try:
            # Query Redis ZSET
            if cursor_data and "score" in cursor_data and "id" in cursor_data:
                # Keyset pagination: start from score <= cursor_score
                max_score = cursor_data["score"]
                raw_entries = redis_client.zrevrangebyscore(
                    REDIS_KEY_POPULAR_24H_GLOBAL,
                    max=max_score,
                    min="-inf",
                    withscores=True,
                )
                # Skip the cursor item itself
                filtered_entries = []
                passed_cursor = False
                for pid, score in raw_entries:
                    if not passed_cursor:
                        if pid == cursor_data["id"]:
                            passed_cursor = True
                        continue
                    filtered_entries.append((pid, score))
                    if len(filtered_entries) >= fetch_limit:
                        break
                scored_entries = filtered_entries
            else:
                scored_entries = redis_client.zrevrange(
                    REDIS_KEY_POPULAR_24H_GLOBAL,
                    0,
                    fetch_limit - 1,
                    withscores=True,
                )

            if scored_entries:
                post_ids = [pid for pid, _ in scored_entries]
                scores_override = {pid: int(score) for pid, score in scored_entries}

                # Hydrate in batch from MongoDB Read Replica
                mongo_query: dict[str, Any] = {
                    "_id": {"$in": post_ids},
                    "is_deleted": False,
                    "is_archived": False,
                }
                if query.source == "forums_only":
                    mongo_query["forum_id"] = {"$ne": None}
                elif query.source == "profiles_only":
                    mongo_query["forum_id"] = None

                doc_map = {str(doc["_id"]): doc for doc in posts_col.find(mongo_query)}

                # Preserve Redis sort order
                ordered_docs = [doc_map[pid] for pid in post_ids if pid in doc_map]

                has_more = len(ordered_docs) > limit
                display_docs = ordered_docs[:limit]

                items = hydrate_feed_items(
                    display_docs,
                    current_user_profile_id=current_user_profile_id,
                    popularity_scores_override=scores_override,
                )

                next_cursor = None
                if has_more and display_docs:
                    last_doc = display_docs[-1]
                    last_id = str(last_doc["_id"])
                    last_score = scores_override.get(last_id, 0)
                    next_cursor = encode_cursor({"score": last_score, "id": last_id})

                return FeedResponseSchema(
                    data=items,
                    pagination=FeedPaginationSchema(
                        next_cursor=next_cursor,
                        has_more=has_more,
                    ),
                )
        except Exception as exc:
            logger.warning("Redis popular feed lookup failed, falling back to Mongo: %s", exc)

    # Route 2: Fallback / Recent / Scoped query via MongoDB
    mongo_filter: dict[str, Any] = {
        "is_deleted": False,
        "is_archived": False,
        "visibility": "PUBLIC",
    }
    if query.source == "forums_only":
        mongo_filter["forum_id"] = {"$ne": None}
    elif query.source == "profiles_only":
        mongo_filter["forum_id"] = None

    cursor_data = decode_cursor(query.cursor)
    if cursor_data:
        if query.sort == "popular" and "score" in cursor_data:
            mongo_filter["popularity_score"] = {"$lte": cursor_data["score"]}
        elif "created_at" in cursor_data:
            try:
                c_date = datetime.fromisoformat(cursor_data["created_at"])
                mongo_filter["created_at"] = {"$lt": c_date}
            except Exception:
                pass

    sort_order = (
        [("popularity_score", -1), ("created_at", -1)]
        if query.sort == "popular"
        else [("created_at", -1)]
    )

    docs = list(posts_col.find(mongo_filter).sort(sort_order).limit(fetch_limit))

    has_more = len(docs) > limit
    display_docs = docs[:limit]

    items = hydrate_feed_items(
        display_docs,
        current_user_profile_id=current_user_profile_id,
    )

    next_cursor = None
    if has_more and display_docs:
        last = display_docs[-1]
        c_at = last.get("created_at")
        iso_c = c_at.isoformat() if isinstance(c_at, datetime) else str(c_at or "")
        next_cursor = encode_cursor(
            {
                "score": last.get("popularity_score", 0),
                "created_at": iso_c,
                "id": str(last["_id"]),
            }
        )

    return FeedResponseSchema(
        data=items,
        pagination=FeedPaginationSchema(
            next_cursor=next_cursor,
            has_more=has_more,
        ),
    )


def get_joined_forums_feed(
    query: ForumsFeedQuerySchema,
    user_profile_id: str,
    joined_forum_ids: list[str] | None = None,
) -> FeedResponseSchema:
    """Retrieve feed containing posts strictly from user's joined forums."""
    limit = max(1, min(query.limit, 50))
    fetch_limit = limit + 1

    # In production, joined_forum_ids is resolved from Forum DB (forum_members)
    # If not provided, query PostgreSQL Forum DB
    if joined_forum_ids is None:
        joined_forum_ids = []
        try:
            conn = connections.get("forum_db") or connections.get("default")
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT forum_id::text
                        FROM forum_members
                        WHERE user_profile_id = %s AND status = 'APPROVED'
                        """,
                        [str(user_profile_id)],
                    )
                    joined_forum_ids = [str(r[0]) for r in cursor.fetchall()]
        except Exception:
            pass

    if not joined_forum_ids:
        # User has joined no forums yet
        return FeedResponseSchema(
            data=[],
            pagination=FeedPaginationSchema(next_cursor=None, has_more=False),
        )

    posts_col = get_mongo_posts_collection()
    mongo_filter: dict[str, Any] = {
        "forum_id": {"$in": joined_forum_ids},
        "is_deleted": False,
        "is_archived": False,
    }

    cursor_data = decode_cursor(query.cursor)
    if cursor_data and "created_at" in cursor_data:
        try:
            c_date = datetime.fromisoformat(cursor_data["created_at"])
            mongo_filter["created_at"] = {"$lt": c_date}
        except Exception:
            pass

    sort_order = (
        [("popularity_score", -1), ("created_at", -1)]
        if query.sort == "popular"
        else [("created_at", -1)]
    )

    docs = list(posts_col.find(mongo_filter).sort(sort_order).limit(fetch_limit))

    has_more = len(docs) > limit
    display_docs = docs[:limit]

    items = hydrate_feed_items(
        display_docs,
        current_user_profile_id=str(user_profile_id),
    )

    next_cursor = None
    if has_more and display_docs:
        last = display_docs[-1]
        c_at = last.get("created_at")
        iso_c = c_at.isoformat() if isinstance(c_at, datetime) else str(c_at or "")
        next_cursor = encode_cursor(
            {
                "score": last.get("popularity_score", 0),
                "created_at": iso_c,
                "id": str(last["_id"]),
            }
        )

    return FeedResponseSchema(
        data=items,
        pagination=FeedPaginationSchema(
            next_cursor=next_cursor,
            has_more=has_more,
        ),
    )


def get_following_feed(
    query: FollowingFeedQuerySchema,
    user_profile_id: str,
    followed_profile_ids: list[str] | None = None,
) -> FeedResponseSchema:
    """Retrieve personal timeline containing profile posts of followed creators."""
    limit = max(1, min(query.limit, 50))
    fetch_limit = limit + 1

    # In production, followed_profile_ids is resolved from Auth DB (user_relations)
    if followed_profile_ids is None:
        followed_profile_ids = []
        try:
            conn = connections.get("auth_db") or connections.get("default")
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT target_profile_id::text
                        FROM user_relations
                        WHERE follower_profile_id = %s AND status = 'ACCEPTED'
                        """,
                        [str(user_profile_id)],
                    )
                    followed_profile_ids = [str(r[0]) for r in cursor.fetchall()]
        except Exception:
            pass

    if not followed_profile_ids:
        # User follows no one yet
        return FeedResponseSchema(
            data=[],
            pagination=FeedPaginationSchema(next_cursor=None, has_more=False),
        )

    posts_col = get_mongo_posts_collection()
    mongo_filter: dict[str, Any] = {
        "author_profile_id": {"$in": followed_profile_ids},
        "forum_id": None,
        "visibility": {"$in": ["PUBLIC", "FOLLOWERS_ONLY"]},
        "is_deleted": False,
        "is_archived": False,
    }

    cursor_data = decode_cursor(query.cursor)
    if cursor_data and "created_at" in cursor_data:
        try:
            c_date = datetime.fromisoformat(cursor_data["created_at"])
            mongo_filter["created_at"] = {"$lt": c_date}
        except Exception:
            pass

    sort_order = (
        [("popularity_score", -1), ("created_at", -1)]
        if query.sort == "popular"
        else [("created_at", -1)]
    )

    docs = list(posts_col.find(mongo_filter).sort(sort_order).limit(fetch_limit))

    has_more = len(docs) > limit
    display_docs = docs[:limit]

    items = hydrate_feed_items(
        display_docs,
        current_user_profile_id=str(user_profile_id),
    )

    next_cursor = None
    if has_more and display_docs:
        last = display_docs[-1]
        c_at = last.get("created_at")
        iso_c = c_at.isoformat() if isinstance(c_at, datetime) else str(c_at or "")
        next_cursor = encode_cursor(
            {
                "score": last.get("popularity_score", 0),
                "created_at": iso_c,
                "id": str(last["_id"]),
            }
        )

    return FeedResponseSchema(
        data=items,
        pagination=FeedPaginationSchema(
            next_cursor=next_cursor,
            has_more=has_more,
        ),
    )

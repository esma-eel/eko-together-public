"""MongoDB connection singleton and collection accessors for Post & Comment Service.

Uses PyMongo with a module-level singleton pattern so the connection pool
is initialised once when Django boots and reused across all requests.

Collections:
    - posts: Document store for post metadata (title, body, tags, counters)
    - comments: Threaded comment tree with parent_id / depth enforcement
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pymongo
from django.conf import settings

if TYPE_CHECKING:
    from pymongo.collection import Collection
    from pymongo.database import Database

_client: pymongo.MongoClient | None = None
_database: Database | None = None


def get_client() -> pymongo.MongoClient:
    """Return (or lazily initialise) the MongoClient singleton."""
    global _client
    if _client is None:
        mongo_uri = getattr(settings, "MONGO_URI", "")
        if getattr(settings, "USE_MONGOMOCK", False) or mongo_uri.startswith("mongomock://"):
            import mongomock

            _client = mongomock.MongoClient(uuidRepresentation="standard")
        else:
            timeout = getattr(settings, "MONGO_SERVER_SELECTION_TIMEOUT_MS", 2000)
            _client = pymongo.MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=timeout,
                uuidRepresentation="standard",
            )
    return _client


def get_database() -> Database:
    """Return the application-level MongoDB database handle."""
    global _database
    if _database is None:
        _database = get_client()[settings.MONGO_DATABASE]
    return _database


def reset_db_client() -> None:
    """Reset singleton for test isolation."""
    global _client, _database
    _client = None
    _database = None


def get_posts_collection() -> Collection:
    """Return the 'posts' collection with guaranteed compound indexes."""
    db = get_database()
    col = db["posts"]
    return col


def get_comments_collection() -> Collection:
    """Return the 'comments' collection with guaranteed compound indexes."""
    db = get_database()
    col = db["comments"]
    return col


def ensure_indexes() -> None:
    """Create all required MongoDB indexes if they do not already exist.

    Called once at application startup from the AppConfig.ready() hook.
    Indexes are created with background=True so they do not block startup.
    """
    posts_col = get_posts_collection()

    # Posts: filter by forum, author, tags; sort by created_at / popularity_score
    posts_col.create_index([("forum_id", pymongo.ASCENDING)], background=True)
    posts_col.create_index([("author_profile_id", pymongo.ASCENDING)], background=True)
    posts_col.create_index([("tags", pymongo.ASCENDING)], background=True)
    posts_col.create_index([("created_at", pymongo.DESCENDING)], background=True)
    posts_col.create_index([("popularity_score", pymongo.DESCENDING)], background=True)
    posts_col.create_index(
        [("is_deleted", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
        background=True,
    )

    comments_col = get_comments_collection()

    # Comments: primary lookup pattern is (post_id, depth) for threaded listing
    comments_col.create_index(
        [("post_id", pymongo.ASCENDING), ("created_at", pymongo.ASCENDING)],
        background=True,
    )
    # Fetch children of a parent (for reply count and tree traversal)
    comments_col.create_index(
        [("parent_id", pymongo.ASCENDING)],
        background=True,
    )
    # Compound: shard-friendly key (post_id, _id) for efficient pagination
    comments_col.create_index(
        [("post_id", pymongo.ASCENDING), ("_id", pymongo.ASCENDING)],
        background=True,
    )

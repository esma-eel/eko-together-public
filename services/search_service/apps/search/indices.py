"""Elasticsearch index names, schemas, mappings, and index lifecycle utilities."""

from __future__ import annotations

import logging
from typing import Any

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

INDEX_POSTS = "posts_index"
INDEX_FORUMS = "forums_index"
INDEX_PROFILES = "profiles_index"
INDEX_COMMENTS = "comments_index"

ALL_INDICES = [INDEX_POSTS, INDEX_FORUMS, INDEX_PROFILES, INDEX_COMMENTS]

INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    INDEX_POSTS: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "forum_id": {"type": "keyword"},
                "author_id": {"type": "keyword"},
                "author_display_name": {
                    "type": "text",
                    "fields": {"raw": {"type": "keyword"}},
                },
                "title": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {
                        "suggest": {"type": "search_as_you_type"},
                        "raw": {"type": "keyword"},
                    },
                },
                "body": {"type": "text", "analyzer": "standard"},
                "image": {"type": "keyword"},
                "has_image": {"type": "boolean"},
                "tags": {"type": "keyword"},
                "forum_title": {"type": "text"},
                "forum_slug": {"type": "keyword"},
                "is_pinned": {"type": "boolean"},
                "is_deleted": {"type": "boolean"},
                "visibility": {"type": "keyword"},
                "popularity_score": {"type": "integer"},
                "upvotes_count": {"type": "integer"},
                "downvotes_count": {"type": "integer"},
                "created_at": {"type": "date"},
            }
        }
    },
    INDEX_FORUMS: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {
                        "suggest": {"type": "search_as_you_type"},
                        "raw": {"type": "keyword"},
                    },
                },
                "slug": {
                    "type": "keyword",
                    "fields": {"text": {"type": "text"}},
                },
                "description": {"type": "text", "analyzer": "standard"},
                "avatar": {"type": "keyword"},
                "cover_image": {"type": "keyword"},
                "owner_id": {"type": "keyword"},
                "owner_display_name": {"type": "text"},
                "require_approval_to_join": {"type": "boolean"},
                "post_permission": {"type": "keyword"},
                "is_comments_locked": {"type": "boolean"},
                "members_count": {"type": "integer"},
                "created_at": {"type": "date"},
            }
        }
    },
    INDEX_PROFILES: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "username": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {
                        "suggest": {"type": "search_as_you_type"},
                        "raw": {"type": "keyword"},
                    },
                },
                "display_name": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {
                        "suggest": {"type": "search_as_you_type"},
                    },
                },
                "bio": {"type": "text", "analyzer": "standard"},
                "avatar": {"type": "keyword"},
                "is_private": {"type": "boolean"},
                "created_at": {"type": "date"},
            }
        }
    },
    INDEX_COMMENTS: {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "post_id": {"type": "keyword"},
                "post_title": {"type": "text"},
                "forum_id": {"type": "keyword"},
                "author_id": {"type": "keyword"},
                "author_display_name": {"type": "text"},
                "body": {"type": "text", "analyzer": "standard"},
                "parent_id": {"type": "keyword"},
                "depth": {"type": "integer"},
                "popularity_score": {"type": "integer"},
                "is_deleted": {"type": "boolean"},
                "created_at": {"type": "date"},
            }
        }
    },
}


def setup_all_indices(client: Elasticsearch, recreate: bool = False) -> dict[str, str]:
    """Create or update Elasticsearch indices according to blueprint schemas.

    Args:
        client: Active Elasticsearch client.
        recreate: If True, deletes existing indices before creating them.

    Returns:
        Summary dict of index status (e.g. {'posts_index': 'created'}).
    """
    status: dict[str, str] = {}
    for index_name, schema in INDEX_MAPPINGS.items():
        exists = client.indices.exists(index=index_name)
        if exists and recreate:
            client.indices.delete(index=index_name)
            exists = False

        if not exists:
            client.indices.create(
                index=index_name,
                mappings=schema.get("mappings"),
                settings=schema.get("settings"),
            )
            status[index_name] = "created"
            logger.info("Created Elasticsearch index: %s", index_name)
        else:
            status[index_name] = "exists"
            logger.info("Elasticsearch index already exists: %s", index_name)
    return status

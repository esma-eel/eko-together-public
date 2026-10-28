"""RabbitMQ Search Event Ingestion Consumer Worker.

Consumes domain events (post.created, post.updated, post.deleted, comment.created,
comment.deleted, forum.created, forum.updated, forum.deleted, profile.updated, vote.cast)
from the search.indexer queue and synchronizes inverted indexes in Elasticsearch asynchronously.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pika
from elasticsearch import Elasticsearch

from services.search_service.apps.search.client import get_elasticsearch_client
from services.search_service.apps.search.indices import (
    INDEX_COMMENTS,
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
)
from shared.events import (
    EXCHANGE_EVENTS,
    QUEUE_SEARCH_INGESTION,
    ROUTING_COMMENT_CREATED,
    ROUTING_COMMENT_DELETED,
    ROUTING_COMMENT_UPDATED,
    ROUTING_FORUM_CREATED,
    ROUTING_FORUM_DELETED,
    ROUTING_FORUM_UPDATED,
    ROUTING_POST_CREATED,
    ROUTING_POST_DELETED,
    ROUTING_POST_UPDATED,
    ROUTING_PROFILE_UPDATED,
    ROUTING_VOTE_CAST,
    ROUTING_VOTE_REVOKED,
    CommentCreatedEvent,
    CommentDeletedEvent,
    CommentUpdatedEvent,
    ForumCreatedEvent,
    ForumDeletedEvent,
    ForumUpdatedEvent,
    PostCreatedEvent,
    PostDeletedEvent,
    PostUpdatedEvent,
    UserProfileUpdatedEvent,
    VoteCastEvent,
    VoteRevokedEvent,
    deserialize_event,
)
from shared.events.publisher import get_rabbitmq_url

logger = logging.getLogger(__name__)


def process_search_event_message(
    body: bytes | str,
    client: Elasticsearch | None = None,
) -> bool:
    """Parse a domain event and synchronize the corresponding Elasticsearch document.

    Args:
        body: Raw JSON message bytes or string.
        client: Optional Elasticsearch client instance (for testing).

    Returns:
        True if the event was successfully ingested or handled, False otherwise.
    """
    es = client or get_elasticsearch_client()

    try:
        raw_dict: dict[str, Any]
        if isinstance(body, bytes):
            raw_dict = json.loads(body.decode("utf-8"))
        else:
            raw_dict = json.loads(body)

        event_type = raw_dict.get("event_type")

        # ----------------------------------------------------------------------
        # Post Events
        # ----------------------------------------------------------------------
        if event_type == "post.created":
            p_event = deserialize_event(body, PostCreatedEvent)
            doc = {
                "id": str(p_event.post_id),
                "forum_id": str(p_event.forum_id) if p_event.forum_id else None,
                "author_id": str(p_event.author_profile_id),
                "author_display_name": p_event.author_display_name or "Author",
                "title": p_event.title,
                "body": p_event.body,
                "image": p_event.image_url,
                "has_image": bool(p_event.image_url),
                "tags": p_event.tags,
                "forum_title": p_event.forum_title or "General",
                "forum_slug": p_event.forum_slug or "general",
                "is_pinned": False,
                "is_deleted": False,
                "visibility": p_event.visibility,
                "popularity_score": 0,
                "upvotes_count": 0,
                "downvotes_count": 0,
                "created_at": p_event.occurred_at,
            }
            es.index(index=INDEX_POSTS, id=str(p_event.post_id), document=doc)
            logger.info("Indexed post into ES: %s", p_event.post_id)
            return True

        elif event_type == "post.updated":
            pu_event = deserialize_event(body, PostUpdatedEvent)
            update_doc: dict[str, Any] = {
                "title": pu_event.title,
                "tags": pu_event.tags,
            }
            if pu_event.body:
                update_doc["body"] = pu_event.body
            if pu_event.image_url is not None:
                update_doc["image"] = pu_event.image_url
                update_doc["has_image"] = bool(pu_event.image_url)
            es.update(
                index=INDEX_POSTS,
                id=str(pu_event.post_id),
                doc=update_doc,
                doc_as_upsert=True,
            )
            logger.info("Updated post in ES: %s", pu_event.post_id)
            return True

        elif event_type == "post.deleted":
            pd_event = deserialize_event(body, PostDeletedEvent)
            es.update(
                index=INDEX_POSTS,
                id=str(pd_event.post_id),
                doc={"is_deleted": True},
                doc_as_upsert=True,
            )
            logger.info("Marked post deleted in ES: %s", pd_event.post_id)
            return True

        # ----------------------------------------------------------------------
        # Comment Events
        # ----------------------------------------------------------------------
        elif event_type == "comment.created":
            c_event = deserialize_event(body, CommentCreatedEvent)
            c_doc = {
                "id": str(c_event.comment_id),
                "post_id": str(c_event.post_id),
                "post_title": c_event.post_title or "Post Discussion",
                "forum_id": str(c_event.forum_id) if c_event.forum_id else None,
                "author_id": str(c_event.user_profile_id),
                "author_display_name": c_event.author_display_name or "Commenter",
                "body": c_event.body,
                "parent_id": str(c_event.parent_id) if c_event.parent_id else None,
                "depth": c_event.depth,
                "popularity_score": 0,
                "is_deleted": False,
                "created_at": c_event.occurred_at,
            }
            es.index(index=INDEX_COMMENTS, id=str(c_event.comment_id), document=c_doc)
            logger.info("Indexed comment into ES: %s", c_event.comment_id)
            return True

        elif event_type == "comment.updated":
            cu_event = deserialize_event(body, CommentUpdatedEvent)
            es.update(
                index=INDEX_COMMENTS,
                id=str(cu_event.comment_id),
                doc={"body": cu_event.body},
                doc_as_upsert=True,
            )
            logger.info("Updated comment in ES: %s", cu_event.comment_id)
            return True

        elif event_type == "comment.deleted":
            cd_event = deserialize_event(body, CommentDeletedEvent)
            es.update(
                index=INDEX_COMMENTS,
                id=str(cd_event.comment_id),
                doc={"is_deleted": True},
                doc_as_upsert=True,
            )
            logger.info("Marked comment deleted in ES: %s", cd_event.comment_id)
            return True

        # ----------------------------------------------------------------------
        # Forum Events
        # ----------------------------------------------------------------------
        elif event_type == "forum.created":
            f_event = deserialize_event(body, ForumCreatedEvent)
            f_doc = {
                "id": str(f_event.forum_id),
                "title": f_event.title,
                "slug": f_event.slug,
                "description": f_event.description or "",
                "avatar": f_event.avatar,
                "cover_image": f_event.cover_image,
                "owner_id": str(f_event.owner_profile_id),
                "owner_display_name": f_event.owner_display_name or "Forum Owner",
                "require_approval_to_join": f_event.require_approval_to_join,
                "post_permission": f_event.post_permission,
                "is_comments_locked": False,
                "members_count": 1,
                "created_at": f_event.occurred_at,
            }
            es.index(index=INDEX_FORUMS, id=str(f_event.forum_id), document=f_doc)
            logger.info("Indexed forum into ES: %s", f_event.forum_id)
            return True

        elif event_type == "forum.updated":
            fu_event = deserialize_event(body, ForumUpdatedEvent)
            update_fdoc: dict[str, Any] = {
                "title": fu_event.title,
                "slug": fu_event.slug,
                "is_comments_locked": fu_event.is_comments_locked,
                "post_permission": fu_event.post_permission,
            }
            if fu_event.description:
                update_fdoc["description"] = fu_event.description
            if fu_event.avatar:
                update_fdoc["avatar"] = fu_event.avatar
            if fu_event.cover_image:
                update_fdoc["cover_image"] = fu_event.cover_image
            es.update(
                index=INDEX_FORUMS,
                id=str(fu_event.forum_id),
                doc=update_fdoc,
                doc_as_upsert=True,
            )
            logger.info("Updated forum in ES: %s", fu_event.forum_id)
            return True

        elif event_type == "forum.deleted":
            fd_event = deserialize_event(body, ForumDeletedEvent)
            try:
                es.delete(index=INDEX_FORUMS, id=str(fd_event.forum_id))
            except Exception:
                pass
            logger.info("Deleted forum from ES: %s", fd_event.forum_id)
            return True

        # ----------------------------------------------------------------------
        # Profile Events
        # ----------------------------------------------------------------------
        elif event_type == "profile.updated":
            pr_event = deserialize_event(body, UserProfileUpdatedEvent)
            pr_doc = {
                "id": str(pr_event.profile_id),
                "user_id": str(pr_event.user_id),
                "username": pr_event.username,
                "display_name": pr_event.display_name,
                "bio": pr_event.bio,
                "avatar": pr_event.avatar,
                "is_private": pr_event.is_private,
                "created_at": pr_event.occurred_at,
            }
            es.update(
                index=INDEX_PROFILES,
                id=str(pr_event.profile_id),
                doc=pr_doc,
                doc_as_upsert=True,
            )
            logger.info("Upserted profile into ES: %s", pr_event.profile_id)
            return True

        # ----------------------------------------------------------------------
        # Vote Events
        # ----------------------------------------------------------------------
        elif event_type == "vote.cast":
            v_event = deserialize_event(body, VoteCastEvent)
            target_index = INDEX_POSTS if v_event.target_type == "POST" else INDEX_COMMENTS
            # Update popularity score script or doc
            script = {
                "source": (
                    "ctx._source.upvotes_count = (ctx._source.upvotes_count ?: 0) + params.up; "
                    "ctx._source.downvotes_count = "
                    "(ctx._source.downvotes_count ?: 0) + params.down; "
                    "ctx._source.popularity_score = "
                    "(ctx._source.popularity_score ?: 0) + params.net;"
                ),
                "params": {
                    "up": v_event.delta_up,
                    "down": v_event.delta_down,
                    "net": v_event.net_delta,
                },
            }
            try:
                es.update(index=target_index, id=str(v_event.target_id), script=script)
            except Exception as exc:
                logger.warning(
                    "Could not update ES vote counters for %s: %s", v_event.target_id, exc
                )
            return True

        elif event_type == "vote.revoked":
            vr_event = deserialize_event(body, VoteRevokedEvent)
            target_index = INDEX_POSTS if vr_event.target_type == "POST" else INDEX_COMMENTS
            delta_up = -1 if vr_event.previous_value == 1 else 0
            delta_down = -1 if vr_event.previous_value == -1 else 0
            net_delta = -1 if vr_event.previous_value == 1 else 1
            script = {
                "source": (
                    "ctx._source.upvotes_count = "
                    "Math.max(0, (ctx._source.upvotes_count ?: 0) + params.up); "
                    "ctx._source.downvotes_count = "
                    "Math.max(0, (ctx._source.downvotes_count ?: 0) + params.down); "
                    "ctx._source.popularity_score = "
                    "(ctx._source.popularity_score ?: 0) + params.net;"
                ),
                "params": {
                    "up": delta_up,
                    "down": delta_down,
                    "net": net_delta,
                },
            }
            try:
                es.update(index=target_index, id=str(vr_event.target_id), script=script)
            except Exception as exc:
                logger.warning(
                    "Could not revoke ES vote counters for %s: %s", vr_event.target_id, exc
                )
            return True

        else:
            logger.debug("Ignoring unhandled event type: %s", event_type)
            return True

    except Exception as exc:
        logger.error("Failed to process search ingestion event: %s", exc, exc_info=True)
        return False


def start_search_consumer(
    rabbitmq_url: str | None = None,
    client: Elasticsearch | None = None,
) -> None:
    """Start blocking RabbitMQ consumer loop on search.indexer queue."""
    url = rabbitmq_url or get_rabbitmq_url()
    params = pika.URLParameters(url)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.exchange_declare(
        exchange=EXCHANGE_EVENTS,
        exchange_type="topic",
        durable=True,
    )
    channel.queue_declare(queue=QUEUE_SEARCH_INGESTION, durable=True)

    routing_keys = [
        ROUTING_POST_CREATED,
        ROUTING_POST_UPDATED,
        ROUTING_POST_DELETED,
        ROUTING_COMMENT_CREATED,
        ROUTING_COMMENT_UPDATED,
        ROUTING_COMMENT_DELETED,
        ROUTING_FORUM_CREATED,
        ROUTING_FORUM_UPDATED,
        ROUTING_FORUM_DELETED,
        ROUTING_PROFILE_UPDATED,
        ROUTING_VOTE_CAST,
        ROUTING_VOTE_REVOKED,
    ]

    for key in routing_keys:
        channel.queue_bind(
            queue=QUEUE_SEARCH_INGESTION,
            exchange=EXCHANGE_EVENTS,
            routing_key=key,
        )

    logger.info("Search consumer listening on queue: %s", QUEUE_SEARCH_INGESTION)

    def on_message(
        ch: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.BasicProperties,
        body: bytes,
    ) -> None:
        success = process_search_event_message(body, client=client)
        if success:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_qos(prefetch_count=50)
    channel.basic_consume(
        queue=QUEUE_SEARCH_INGESTION,
        on_message_callback=on_message,
        auto_ack=False,
    )

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()

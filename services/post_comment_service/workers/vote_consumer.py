"""RabbitMQ Vote Event Consumer Worker.

Consumes VoteCastEvent and VoteRevokedEvent from the posts.counter_updates queue
and applies atomic bulk $inc updates to MongoDB posts and comments collections.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import pika

from services.post_comment_service.db import (
    get_comments_collection,
    get_posts_collection,
)
from shared.events import (
    EXCHANGE_EVENTS,
    QUEUE_POST_COUNTERS,
    ROUTING_VOTE_CAST,
    ROUTING_VOTE_REVOKED,
    VoteCastEvent,
    VoteRevokedEvent,
    deserialize_event,
)
from shared.events.publisher import get_rabbitmq_url

logger = logging.getLogger(__name__)


def update_target_counters(
    *,
    target_type: str,
    target_id: str | UUID,
    delta_up: int,
    delta_down: int,
    net_delta: int,
) -> bool:
    """Atomically increment/decrement upvotes, downvotes, and popularity score in MongoDB."""
    target_id_str = str(target_id)
    inc_payload = {
        "upvotes_count": delta_up,
        "downvotes_count": delta_down,
        "popularity_score": net_delta,
    }

    if target_type.upper() == "POST":
        posts = get_posts_collection()
        result = posts.update_one(
            {"_id": target_id_str},
            {"$inc": inc_payload},
        )
        matched = result.matched_count > 0
        if not matched:
            logger.warning("Post document %s not found for counter increment", target_id_str)
        return matched

    elif target_type.upper() == "COMMENT":
        comments = get_comments_collection()
        result = comments.update_one(
            {"_id": target_id_str},
            {"$inc": inc_payload},
        )
        matched = result.matched_count > 0
        if not matched:
            logger.warning("Comment document %s not found for counter increment", target_id_str)
        return matched

    else:
        logger.error("Unknown target_type %s for voting event", target_type)
        return False


def process_vote_event_message(body: bytes | str) -> bool:
    """Parse and dispatch a single raw RabbitMQ message body to MongoDB counters.

    Args:
        body: Raw JSON payload bytes or string.

    Returns:
        True if successfully handled, False otherwise.
    """
    try:
        # Inspect event_type without full deserialization first
        raw_dict: dict[str, Any]
        if isinstance(body, bytes):
            raw_dict = json.loads(body.decode("utf-8"))
        else:
            raw_dict = json.loads(body)

        event_type = raw_dict.get("event_type")

        if event_type == "vote.cast":
            cast_event = deserialize_event(body, VoteCastEvent)
            return update_target_counters(
                target_type=cast_event.target_type,
                target_id=cast_event.target_id,
                delta_up=cast_event.delta_up,
                delta_down=cast_event.delta_down,
                net_delta=cast_event.net_delta,
            )

        elif event_type == "vote.revoked":
            revoked_event = deserialize_event(body, VoteRevokedEvent)
            prev = revoked_event.previous_value
            delta_up = -1 if prev == 1 else 0
            delta_down = -1 if prev == -1 else 0
            net_delta = -1 if prev == 1 else 1

            return update_target_counters(
                target_type=revoked_event.target_type,
                target_id=revoked_event.target_id,
                delta_up=delta_up,
                delta_down=delta_down,
                net_delta=net_delta,
            )

        else:
            logger.warning("Ignored non-voting event in counter worker: %s", event_type)
            return True

    except Exception as exc:
        logger.error("Failed to process vote event message: %s", exc, exc_info=True)
        return False


def start_vote_consumer(
    *,
    queue_name: str = QUEUE_POST_COUNTERS,
    exchange_name: str = EXCHANGE_EVENTS,
    prefetch_count: int = 50,
    max_messages: int | None = None,
) -> int:
    """Start blocking RabbitMQ consumer loop for vote events.

    Args:
        queue_name: Queue to declare and consume from.
        exchange_name: Main topic exchange to bind against.
        prefetch_count: Max unacknowledged messages per worker.
        max_messages: Optional limit for testing/single-batch runs.

    Returns:
        Number of processed messages.
    """
    url = get_rabbitmq_url()
    params = pika.URLParameters(url)
    params.socket_timeout = 5.0

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    # Declare exchange and durable queue
    channel.exchange_declare(
        exchange=exchange_name,
        exchange_type="topic",
        durable=True,
    )
    channel.queue_declare(queue=queue_name, durable=True)

    # Bind queue to vote routing keys
    channel.queue_bind(
        queue=queue_name,
        exchange=exchange_name,
        routing_key=ROUTING_VOTE_CAST,
    )
    channel.queue_bind(
        queue=queue_name,
        exchange=exchange_name,
        routing_key=ROUTING_VOTE_REVOKED,
    )

    channel.basic_qos(prefetch_count=prefetch_count)

    processed_count = 0

    def on_message(ch, method, properties, body):
        nonlocal processed_count
        success = process_vote_event_message(body)
        if success:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # Requeue on unexpected error
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

        processed_count += 1
        if max_messages is not None and processed_count >= max_messages:
            ch.stop_consuming()

    channel.basic_consume(
        queue=queue_name,
        on_message_callback=on_message,
        auto_ack=False,
    )

    logger.info("Starting vote consumer on queue '%s'...", queue_name)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("Vote consumer stopped by user.")
        channel.stop_consuming()
    finally:
        if connection.is_open:
            connection.close()

    return processed_count

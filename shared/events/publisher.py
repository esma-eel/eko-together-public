"""RabbitMQ Domain Event Publisher.

Publishes typed BaseEvent instances to the shared topic exchange.
Supports persistent delivery mode and graceful degradation when broker is unreachable.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import pika
from django.conf import settings

from shared.events.base import BaseEvent, serialize_event
from shared.events.constants import EXCHANGE_EVENTS

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def get_rabbitmq_url() -> str:
    """Return normalized RabbitMQ URL with IPv4 fallback and default vhost."""
    url = getattr(settings, "RABBITMQ_URL", os.getenv("RABBITMQ_URL", ""))
    if not url:
        host = getattr(settings, "RABBITMQ_HOST", os.getenv("RABBITMQ_HOST", "127.0.0.1"))
        if host == "localhost":
            host = "127.0.0.1"
        port = getattr(settings, "RABBITMQ_AMQP_PORT", os.getenv("RABBITMQ_AMQP_PORT", "5672"))
        user = getattr(settings, "RABBITMQ_DEFAULT_USER", os.getenv("RABBITMQ_DEFAULT_USER", "rabbit_user"))
        password = getattr(
            settings, "RABBITMQ_DEFAULT_PASS", os.getenv("RABBITMQ_DEFAULT_PASS", "rabbit_password")
        )
        return f"amqp://{user}:{password}@{host}:{port}/%2F"

    # Replace localhost with 127.0.0.1 to avoid IPv6 timeout in Linux/WSL
    if "@localhost:" in url:
        url = url.replace("@localhost:", "@127.0.0.1:")

    # Ensure vhost ends cleanly with /%2F if trailing // exists
    if url.endswith("//"):
        url = url[:-2] + "/%2F"

    return url


def publish_domain_event(
    event: BaseEvent,
    routing_key: str | None = None,
    *,
    exchange: str = EXCHANGE_EVENTS,
) -> bool:
    """Publish a domain event to the RabbitMQ topic exchange.

    Args:
        event: Instance of BaseEvent.
        routing_key: Specific routing key; defaults to event.event_type.
        exchange: Exchange name; defaults to EXCHANGE_EVENTS.

    Returns:
        True if published successfully, False otherwise.
    """
    # Allow test environments to bypass broker calls
    if getattr(settings, "DISABLE_RABBITMQ_FOR_TESTS", False):
        return True

    key = routing_key or event.event_type
    body = serialize_event(event)

    try:
        url = get_rabbitmq_url()
        params = pika.URLParameters(url)
        params.socket_timeout = 2.0

        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        # Ensure durable topic exchange exists
        channel.exchange_declare(
            exchange=exchange,
            exchange_type="topic",
            durable=True,
        )

        channel.basic_publish(
            exchange=exchange,
            routing_key=key,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
            ),
        )

        connection.close()
        return True
    except Exception as exc:
        logger.warning(
            "Failed to publish event %s (%s) to RabbitMQ: %s",
            event.event_type,
            key,
            exc,
        )
        return False

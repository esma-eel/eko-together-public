"""Elasticsearch client provider and lifecycle management."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

_es_client: Elasticsearch | None = None


def get_elasticsearch_client() -> Elasticsearch:
    """Retrieve or initialize the singleton Elasticsearch client."""
    global _es_client
    if _es_client is not None:
        return _es_client

    es_url = getattr(settings, "ELASTICSEARCH_URL", "http://localhost:9200")
    timeout = getattr(settings, "ELASTICSEARCH_TIMEOUT", 10)

    _es_client = Elasticsearch(
        hosts=[es_url],
        request_timeout=timeout,
        max_retries=3,
        retry_on_timeout=True,
    )
    return _es_client


def set_elasticsearch_client(client: Elasticsearch | Any) -> None:
    """Explicitly inject an Elasticsearch client instance (e.g., for tests or mocking)."""
    global _es_client
    _es_client = client


def reset_elasticsearch_client() -> None:
    """Reset the singleton Elasticsearch client."""
    global _es_client
    if _es_client is not None:
        try:
            _es_client.close()
        except Exception:
            pass
    _es_client = None

"""Periodic tasks and worker routines for Feed Service.

Can be dispatched via Celery Beat or run synchronously inside background commands.
"""

from __future__ import annotations

import logging
from typing import Any

from services.feed_service.apps.feed.services import compute_24h_sliding_window

logger = logging.getLogger(__name__)


def compute_24h_sliding_window_task() -> dict[str, Any]:
    """Execute the 24-hour sliding window aggregation job."""
    logger.info("Starting periodic 24-hour sliding window feed computation...")
    result = compute_24h_sliding_window()
    logger.info("24-hour sliding window task finished: %s", result)
    return result

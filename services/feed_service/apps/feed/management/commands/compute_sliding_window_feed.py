"""Django Management Command to execute CQRS 24-hour sliding window feed computation."""

from __future__ import annotations

import sys
import time
from typing import Any

from django.core.management.base import BaseCommand

from services.feed_service.apps.feed.services import compute_24h_sliding_window


class Command(BaseCommand):
    help = (
        "Compute 24-hour sliding window net popularity scores "
        "from Voting DB into Redis Sorted Sets."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=int,
            default=0,
            help="Interval in seconds for periodic execution (0 for single run, e.g. 900).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            default=True,
            help="Run the computation once and exit immediately.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        interval = options.get("interval", 0)

        if interval > 0:
            self.stdout.write(
                self.style.NOTICE(
                    f"Starting periodic CQRS sliding window aggregator every {interval} seconds..."
                )
            )
            try:
                while True:
                    result = compute_24h_sliding_window()
                    count = result.get("posts_ranked", 0)
                    status = result.get("status")
                    ts = result.get("timestamp")
                    self.stdout.write(
                        self.style.SUCCESS(f"[{ts}] Ranked {count} posts. Status: {status}")
                    )
                    time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Periodic aggregator stopped by user."))
                sys.exit(0)
        else:
            self.stdout.write(
                self.style.NOTICE("Running one-shot CQRS 24h sliding window calculation...")
            )
            result = compute_24h_sliding_window()
            if result.get("status") == "success":
                count = result.get("posts_ranked", 0)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully computed 24h popular feed: {count} posts indexed in Redis."
                    )
                )
            else:
                err = result.get("error")
                self.stdout.write(
                    self.style.ERROR(f"Sliding window computation encountered an error: {err}")
                )

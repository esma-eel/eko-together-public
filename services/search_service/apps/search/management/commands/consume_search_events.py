"""Django management command to run the RabbitMQ Search Ingestion Consumer Worker."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from services.search_service.workers.search_consumer import start_search_consumer


class Command(BaseCommand):
    help = "Starts the RabbitMQ Search Ingestion Consumer Worker listening for domain events."

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write(self.style.NOTICE("Starting RabbitMQ Search Ingestion Consumer..."))
        try:
            start_search_consumer()
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Search consumer stopped gracefully."))

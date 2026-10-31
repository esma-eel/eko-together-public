"""Django management command to create or recreate Elasticsearch indices."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from services.search_service.apps.search.client import get_elasticsearch_client
from services.search_service.apps.search.indices import setup_all_indices


class Command(BaseCommand):
    help = "Initializes or recreates Elasticsearch indices and mappings for Search Service."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Delete and recreate indices from scratch (wipes index data).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        recreate = bool(options.get("recreate", False))
        self.stdout.write(
            self.style.NOTICE(f"Setting up Elasticsearch indices (recreate={recreate})...")
        )

        client = get_elasticsearch_client()
        status = setup_all_indices(client, recreate=recreate)

        for index_name, result in status.items():
            color = self.style.SUCCESS if result == "created" else self.style.WARNING
            self.stdout.write(color(f"  [{result.upper()}] {index_name}"))

        self.stdout.write(self.style.SUCCESS("Elasticsearch indices setup completed successfully."))

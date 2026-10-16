"""Management command to start the RabbitMQ vote event consumer worker."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from services.post_comment_service.workers.vote_consumer import start_vote_consumer


class Command(BaseCommand):
    """Run the RabbitMQ consumer worker for updating MongoDB post/comment counters."""

    help = "Consumes vote events from RabbitMQ and updates MongoDB post and comment counters."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-messages",
            type=int,
            default=None,
            help="Stop consuming after processing this many messages.",
        )
        parser.add_argument(
            "--prefetch",
            type=int,
            default=50,
            help="RabbitMQ basic_qos prefetch count.",
        )

    def handle(self, *args, **options):
        max_messages = options.get("max_messages")
        prefetch = options.get("prefetch", 50)

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting Vote Event Consumer (prefetch={prefetch}, max_messages={max_messages})..."
            )
        )
        processed = start_vote_consumer(
            prefetch_count=prefetch,
            max_messages=max_messages,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Finished consuming. Processed {processed} messages.")
        )

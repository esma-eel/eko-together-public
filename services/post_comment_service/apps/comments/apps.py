"""AppConfig for Comments application."""

from __future__ import annotations

import sys

from django.apps import AppConfig


class CommentsConfig(AppConfig):
    """Django app configuration for the Comments domain."""

    name = "services.post_comment_service.apps.comments"
    label = "comments"
    verbose_name = "Comments"

    def ready(self) -> None:
        """Ensure MongoDB indexes exist on startup."""
        # Skip connecting during utility commands like check, makemigrations, etc.
        if any(cmd in sys.argv for cmd in ("check", "makemigrations", "migrate", "collectstatic")):
            return

        from services.post_comment_service.db import ensure_indexes

        try:
            ensure_indexes()
        except Exception:
            # Do not crash Django startup if MongoDB is temporarily unreachable.
            pass

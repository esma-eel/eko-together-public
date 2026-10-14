"""AppConfig for Posts application."""

from __future__ import annotations

import sys

from django.apps import AppConfig


class PostsConfig(AppConfig):
    """Django app configuration for the Posts domain."""

    name = "services.post_comment_service.apps.posts"
    label = "posts"
    verbose_name = "Posts"

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

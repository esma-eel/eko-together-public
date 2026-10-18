"""AppConfig for Votes application in Voting Service."""

from __future__ import annotations

from django.apps import AppConfig


class VotesConfig(AppConfig):
    """Configuration for Votes application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "services.voting_service.apps.votes"
    label = "votes"
    verbose_name = "Votes"

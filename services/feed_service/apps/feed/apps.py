"""AppConfig for Feed App."""

from django.apps import AppConfig


class FeedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.feed_service.apps.feed"
    verbose_name = "Feed and Ranking"

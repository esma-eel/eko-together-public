"""AppConfig for Search app."""

from django.apps import AppConfig


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.search_service.apps.search"
    label = "search"
    verbose_name = "Search Service"

"""Accounts AppConfig."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.auth_user_service.apps.accounts"
    verbose_name = "Accounts & Identity"

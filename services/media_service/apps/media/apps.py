from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services.media_service.apps.media"
    verbose_name = "Media & Object Storage Service"

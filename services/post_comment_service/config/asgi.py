"""ASGI config for Post & Comment Service."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "services.post_comment_service.config.settings",
)

application = get_asgi_application()

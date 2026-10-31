"""WSGI config for Post & Comment Service."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "services.post_comment_service.config.settings",
)

application = get_wsgi_application()

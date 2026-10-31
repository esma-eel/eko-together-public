"""ASGI config for Media Service."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.media_service.config.settings")

application = get_asgi_application()

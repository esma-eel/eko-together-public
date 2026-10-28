"""ASGI config for Search Service."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.search_service.config.settings")

application = get_asgi_application()

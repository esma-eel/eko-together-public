"""ASGI config for User & Auth Service."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.auth_user_service.config.settings")

application = get_asgi_application()

"""WSGI config for User & Auth Service."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.auth_user_service.config.settings")

application = get_wsgi_application()

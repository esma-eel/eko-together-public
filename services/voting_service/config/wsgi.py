"""WSGI config for Voting Service."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.voting_service.config.settings")
application = get_wsgi_application()

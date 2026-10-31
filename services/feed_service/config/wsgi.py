"""WSGI config for Feed Service."""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from django.core.wsgi import get_wsgi_application  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "services.feed_service.config.settings")

application = get_wsgi_application()

"""Django settings for Post & Comment Microservice.

Uses MongoDB via PyMongo for post and comment document storage.
"""

from __future__ import annotations

import os
import sys
import warnings
from http import HTTPStatus
from pathlib import Path

from dmr.settings import Settings
from dotenv import load_dotenv

# Base service directory and root repository directory
SERVICE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SERVICE_DIR.parent.parent

# Ensure ROOT_DIR is on sys.path so shared/ and services/ are importable
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Suppress local dev in-memory cache warning for DMR throttling
try:
    from dmr.validation.endpoint_metadata import UnsafeCacheBackendWarning

    warnings.filterwarnings("ignore", category=UnsafeCacheBackendWarning)
except ImportError:
    pass

# Load .env file from root
load_dotenv(ROOT_DIR / ".env")

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "dev-insecure-post-service-secret-key-change-in-production-1122334455",
)

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1")

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party modern REST layer
    "dmr",
    # Local Posts App
    "services.post_comment_service.apps.posts.apps.PostsConfig",
    # Local Comments App
    "services.post_comment_service.apps.comments.apps.CommentsConfig",
]

MIDDLEWARE = [
    "shared.middleware.GatewayEnforcementMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "services.post_comment_service.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "services.post_comment_service.config.wsgi.application"
ASGI_APPLICATION = "services.post_comment_service.config.asgi.application"

# Post & Comment Service does NOT use a relational DB.
# Django still needs a "default" database for auth/sessions/contenttypes.
# We use SQLite in-memory so that Django can boot without a real SQL server.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SERVICE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================================
# MongoDB Configuration (Post & Comment Document Store)
# ============================================================================
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://mongo_admin:mongo_password@localhost:27017/posts_comments_db?authSource=admin",
)
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "posts_comments_db")
USE_MONGOMOCK = os.getenv("USE_MONGOMOCK", "0") in ("1", "true", "True")
MONGO_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "1000"))

# ============================================================================
# RS256 Asymmetric JWT Public Key Configuration (Verification only)
# ============================================================================
JWT_PUBLIC_KEY_PATH = os.getenv(
    "JWT_PUBLIC_KEY_PATH", str(ROOT_DIR / "shared" / "jwt" / "public_key.pem")
)

# ============================================================================
# RabbitMQ Event Bus Configuration (for publishing domain events)
# ============================================================================
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://rabbit_user:rabbit_password@localhost:5672/",
)

# ============================================================================
# Internal Service URLs (for cross-service permission checks)
# ============================================================================
FORUM_SERVICE_BASE_URL = os.getenv("FORUM_SERVICE_BASE_URL", "http://localhost:8002")

# ============================================================================
# django-modern-rest (DMR) Settings
# ============================================================================
DMR_SETTINGS = {
    Settings.validate_responses: True,
    Settings.semantic_responses: True,
    Settings.exclude_validate_responses: {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        HTTPStatus.TOO_MANY_REQUESTS,
    },
}

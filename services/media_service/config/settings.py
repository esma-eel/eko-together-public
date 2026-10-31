"""Django settings for Media Microservice."""

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

# Ensure ROOT_DIR is on sys.path
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
    "SECRET_KEY", "dev-insecure-media-service-secret-key-change-in-production-1122334455"
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
    # Local Media App
    "services.media_service.apps.media.apps.MediaConfig",
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

ROOT_URLCONF = "services.media_service.config.urls"

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

WSGI_APPLICATION = "services.media_service.config.wsgi.application"
ASGI_APPLICATION = "services.media_service.config.asgi.application"

# Database Configuration (Media Service is stateless; minimal SQLite engine for Django runtime)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SERVICE_DIR / "db.sqlite3",
    }
}

# Cache Configuration (Used for DMR throttling counters)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "media-throttle-cache",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# RS256 Asymmetric JWT Public Key Configuration (Verification only in downstream services)
JWT_PUBLIC_KEY_PATH = os.getenv(
    "JWT_PUBLIC_KEY_PATH", str(ROOT_DIR / "shared" / "jwt" / "public_key.pem")
)

# Object Store / S3 / MinIO Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minio_admin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minio_password")
MINIO_USE_SSL = os.getenv("MINIO_USE_SSL", "False").lower() in ("true", "1")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "forum-media")
MINIO_PUBLIC_URL = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000/forum-media")
CDN_BASE_URL = os.getenv("CDN_BASE_URL", MINIO_PUBLIC_URL)
S3_REGION_NAME = os.getenv("AWS_REGION", "us-east-1")

# django-modern-rest (DMR) Settings
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

"""Django settings for Ranking & Feed Microservice.

Powered by CQRS Read Model Architecture, Redis Sorted Sets, and Django Modern REST (DMR).
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
    "SECRET_KEY",
    "dev-insecure-feed-service-secret-key-change-in-production-1234567890",
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
    # Local Feed App
    "services.feed_service.apps.feed.apps.FeedConfig",
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

ROOT_URLCONF = "services.feed_service.config.urls"

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

WSGI_APPLICATION = "services.feed_service.config.wsgi.application"
ASGI_APPLICATION = "services.feed_service.config.asgi.application"

# Database Configuration
# Feed Service is primarily a CQRS Read Service reading from Redis and Mongo Read Replica.
# Default DB is in-memory SQLite for Django runtime state.
# Voting DB (Port 5434) is configured for the 24h sliding window batch aggregator.
if os.getenv("USE_SQLITE_FOR_TESTS", "0") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": SERVICE_DIR / "db.sqlite3",
        },
        "voting_db": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        },
    }
else:
    db_voting_host = os.getenv("POSTGRES_VOTING_HOST", "127.0.0.1")
    if db_voting_host == "localhost":
        db_voting_host = "127.0.0.1"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": SERVICE_DIR / "db.sqlite3",
        },
        "voting_db": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_VOTING_DB", "voting_db"),
            "USER": os.getenv("POSTGRES_VOTING_USER", "voting_user"),
            "PASSWORD": os.getenv("POSTGRES_VOTING_PASSWORD", "voting_password"),
            "HOST": db_voting_host,
            "PORT": int(os.getenv("POSTGRES_VOTING_PORT", "5434")),
            "CONN_MAX_AGE": 60,
        },
    }

# Redis Configuration (Cache & Sorted Set Engine)
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
if REDIS_HOST == "localhost":
    REDIS_HOST = "127.0.0.1"
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_URL = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "feed-throttle-cache",
    }
}

# MongoDB Configuration (Post & Comment Service Read Model)
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://mongo_admin:mongo_password@127.0.0.1:27017/",
)
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "posts_comments_db")

# Asymmetric RS256 JWT Public Key Path
JWT_PUBLIC_KEY_PATH = Path(
    os.getenv("JWT_PUBLIC_KEY_PATH", str(ROOT_DIR / "shared" / "jwt" / "public_key.pem"))
)

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DMR Configuration
DMR_SETTINGS = {
    Settings.validate_responses: True,
    Settings.semantic_responses: True,
    Settings.exclude_validate_responses: {
        HTTPStatus.UNPROCESSABLE_ENTITY,
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.CONFLICT,
        HTTPStatus.TOO_MANY_REQUESTS,
    },
}

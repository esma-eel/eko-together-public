"""Django settings for Dedicated Voting Microservice.

Connects to dedicated PostgreSQL database (port 5434) and shared Redis cache.
Uses DMR (django-modern-rest) with MsgspecSerializer.
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
    "dev-insecure-voting-service-secret-key-change-in-production-9988776655",
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
    # Local Votes App
    "services.voting_service.apps.votes.apps.VotesConfig",
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

ROOT_URLCONF = "services.voting_service.config.urls"

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

WSGI_APPLICATION = "services.voting_service.config.wsgi.application"
ASGI_APPLICATION = "services.voting_service.config.asgi.application"

# Dedicated PostgreSQL Database Configuration (Port 5434)
if os.getenv("USE_SQLITE_FOR_TESTS", "0") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    # Use 127.0.0.1 default to avoid WSL IPv6 resolution delays
    db_host = os.getenv("POSTGRES_VOTING_HOST", "127.0.0.1")
    if db_host == "localhost":
        db_host = "127.0.0.1"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_VOTING_DB", "voting_db"),
            "USER": os.getenv("POSTGRES_VOTING_USER", "voting_user"),
            "PASSWORD": os.getenv("POSTGRES_VOTING_PASSWORD", "voting_password"),
            "HOST": db_host,
            "PORT": os.getenv("POSTGRES_VOTING_PORT", "5434"),
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = []

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis Cache Backend
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
if "@localhost:" in REDIS_URL:
    REDIS_URL = REDIS_URL.replace("@localhost:", "@127.0.0.1:")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "voting-locmem-cache",
    },
    "redis": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    },
}

# Message Broker: RabbitMQ
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rabbit_user:rabbit_password@127.0.0.1:5672/%2F")
if "@localhost:" in RABBITMQ_URL:
    RABBITMQ_URL = RABBITMQ_URL.replace("@localhost:", "@127.0.0.1:")
if RABBITMQ_URL.endswith("//"):
    RABBITMQ_URL = RABBITMQ_URL[:-2] + "/%2F"

# Asymmetric RS256 JWT Settings
JWT_PUBLIC_KEY_PATH = ROOT_DIR / os.getenv("JWT_PUBLIC_KEY_PATH", "keys/public_key.pem")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "RS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "eko-together-auth-service")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "eko-together-api")

# MongoDB connection for verifying post/comment existence before voting
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://mongo_admin:mongo_password@127.0.0.1:27017/posts_comments_db?authSource=admin",
)
if "@localhost:" in MONGO_URI:
    MONGO_URI = MONGO_URI.replace("@localhost:", "@127.0.0.1:")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "posts_comments_db")

# DMR Configuration
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

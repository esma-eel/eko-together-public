"""Django settings for Forum Microservice."""

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
    "SECRET_KEY", "dev-insecure-forum-service-secret-key-change-in-production-0987654321"
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
    # Local Forums App
    "services.forum_service.apps.forums.apps.ForumsConfig",
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

ROOT_URLCONF = "services.forum_service.config.urls"

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

WSGI_APPLICATION = "services.forum_service.config.wsgi.application"
ASGI_APPLICATION = "services.forum_service.config.asgi.application"

# Database Configuration (PostgreSQL 2: Forum Service - Port 5433)
# Supports in-memory SQLite if USE_SQLITE_FOR_TESTS is set
if os.getenv("USE_SQLITE_FOR_TESTS") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_FORUM_DB", "forum_db"),
            "USER": os.getenv("POSTGRES_FORUM_USER", "forum_user"),
            "PASSWORD": os.getenv("POSTGRES_FORUM_PASSWORD", "forum_password"),
            "HOST": os.getenv("POSTGRES_FORUM_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_FORUM_PORT", "5433"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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

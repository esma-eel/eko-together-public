"""Django settings for User & Authentication Microservice."""

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
    "SECRET_KEY", "dev-insecure-django-secret-key-change-in-production-1234567890"
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
    # Local Accounts App
    "services.auth_user_service.apps.accounts.apps.AccountsConfig",
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

ROOT_URLCONF = "services.auth_user_service.config.urls"

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

WSGI_APPLICATION = "services.auth_user_service.config.wsgi.application"
ASGI_APPLICATION = "services.auth_user_service.config.asgi.application"

# Database Configuration (PostgreSQL 1: User & Auth Service)
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
            "NAME": os.getenv("POSTGRES_AUTH_DB", "auth_db"),
            "USER": os.getenv("POSTGRES_AUTH_USER", "auth_user"),
            "PASSWORD": os.getenv("POSTGRES_AUTH_PASSWORD", "auth_password"),
            "HOST": os.getenv("POSTGRES_AUTH_HOST", "localhost"),
            "PORT": int(os.getenv("POSTGRES_AUTH_PORT", "5432")),
        }
    }

# Custom User Model
AUTH_USER_MODEL = "accounts.User"

# Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# JWT RS256 Key Configuration
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "RS256")
JWT_ACCESS_EXPIRATION_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRATION_MINUTES", "60"))
JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", "7"))
JWT_ISSUER = os.getenv("JWT_ISSUER", "eko-together-auth-service")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "eko-together-api")

_priv_path = os.getenv("JWT_PRIVATE_KEY_PATH", "keys/private_key.pem")
_pub_path = os.getenv("JWT_PUBLIC_KEY_PATH", "keys/public_key.pem")

JWT_PRIVATE_KEY_PATH = (
    ROOT_DIR / _priv_path if not Path(_priv_path).is_absolute() else Path(_priv_path)
)
JWT_PUBLIC_KEY_PATH = ROOT_DIR / _pub_path if not Path(_pub_path).is_absolute() else Path(_pub_path)

# DMR Framework Settings
DMR_SETTINGS = {
    Settings.exclude_validate_responses: {
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.CONFLICT,
        HTTPStatus.UNPROCESSABLE_ENTITY,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.INTERNAL_SERVER_ERROR,
    },
}

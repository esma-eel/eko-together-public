"""Root pytest configuration and fixtures."""

import os
import sys
from pathlib import Path

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Configure unified Django settings module for tests
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")
os.environ.setdefault("USE_SQLITE_FOR_TESTS", "1")

import django  # noqa: E402

django.setup()

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    """Ensure in-memory throttle cache is cleared between tests."""
    cache.clear()
    yield
    cache.clear()

"""Shared fixtures for Auth & User Service test suite."""

import pytest
from dmr.test import DMRClient, DMRRequestFactory

from services.auth_user_service.apps.accounts.models import (
    CommentPermissionChoices,
    PostVisibilityChoices,
    User,
    UserProfile,
)
from services.auth_user_service.apps.accounts.services import create_user_tokens


@pytest.fixture
def client() -> DMRClient:
    """Fixture providing DMR test client with JSON content negotiation."""
    return DMRClient()


@pytest.fixture
def rf() -> DMRRequestFactory:
    """Fixture providing DMR request factory."""
    return DMRRequestFactory()


@pytest.fixture
def user_a(db) -> User:
    """Standard public test user A."""
    user = User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="AliceSecurePassword123!",
    )
    UserProfile.objects.create(
        user=user,
        display_name="Alice Smith",
        bio="Hello, I am Alice.",
        is_private=False,
    )
    return user


@pytest.fixture
def user_b(db) -> User:
    """Standard public test user B."""
    user = User.objects.create_user(
        username="bob",
        email="bob@example.com",
        password="BobSecurePassword123!",
    )
    UserProfile.objects.create(
        user=user,
        display_name="Bob Builder",
        bio="Bob's bio.",
        is_private=False,
    )
    return user


@pytest.fixture
def private_user(db) -> User:
    """Test user with a strictly private profile."""
    user = User.objects.create_user(
        username="clara_private",
        email="clara@example.com",
        password="ClaraSecurePassword123!",
    )
    UserProfile.objects.create(
        user=user,
        display_name="Clara Private",
        bio="Confidential profile notes.",
        is_private=True,
        default_post_visibility=PostVisibilityChoices.FOLLOWERS_ONLY,
        default_comment_permission=CommentPermissionChoices.FOLLOWERS_ONLY,
    )
    return user


@pytest.fixture
def auth_headers_a(user_a: User) -> dict[str, str]:
    """Authorization header with valid RS256 token for user_a."""
    access, _ = create_user_tokens(user_a)
    return {"HTTP_AUTHORIZATION": f"Bearer {access}"}


@pytest.fixture
def auth_headers_b(user_b: User) -> dict[str, str]:
    """Authorization header with valid RS256 token for user_b."""
    access, _ = create_user_tokens(user_b)
    return {"HTTP_AUTHORIZATION": f"Bearer {access}"}


@pytest.fixture
def auth_headers_private(private_user: User) -> dict[str, str]:
    """Authorization header with valid RS256 token for private_user."""
    access, _ = create_user_tokens(private_user)
    return {"HTTP_AUTHORIZATION": f"Bearer {access}"}

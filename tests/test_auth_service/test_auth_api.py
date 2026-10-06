"""Tests for Authentication endpoints (/api/v1/auth/)."""

from http import HTTPStatus

import pytest
from dmr.test import DMRClient

from services.auth_user_service.apps.accounts.models import (
    User,
    UserActionLog,
)
from services.auth_user_service.apps.accounts.services import (
    create_user_tokens,
    encode_user_id,
    password_reset_token_generator,
)


@pytest.mark.django_db
def test_signup_success(client: DMRClient) -> None:
    """Validate user registration issues RS256 tokens and creates profile."""
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "StrongPassword999!",
        "display_name": "New User",
    }
    response = client.post("/api/v1/auth/signup/", data=payload)
    assert response.status_code == HTTPStatus.CREATED
    data = response.json()

    # Verify response structure
    assert "user" in data
    assert data["user"]["username"] == "newuser"
    assert data["user"]["email"] == "newuser@example.com"
    assert "id" in data["user"]

    assert "profile" in data
    assert data["profile"]["display_name"] == "New User"
    assert "id" in data["profile"]

    assert "tokens" in data
    assert "access" in data["tokens"]
    assert "refresh" in data["tokens"]

    # Verify DB persistence
    user = User.objects.get(username="newuser")
    assert user.email == "newuser@example.com"
    assert user.profile.display_name == "New User"

    # Verify audit log
    log = UserActionLog.objects.filter(action="SIGNUP", user_profile=user.profile).first()
    assert log is not None
    assert log.target_id == str(user.id)


@pytest.mark.django_db
def test_signup_duplicate_username(client: DMRClient, user_a: User) -> None:
    """Duplicate username registration returns 409 Conflict."""
    payload = {
        "username": user_a.username,
        "email": "different@example.com",
        "password": "StrongPassword999!",
        "display_name": "Different Name",
    }
    response = client.post("/api/v1/auth/signup/", data=payload)
    assert response.status_code == HTTPStatus.CONFLICT


@pytest.mark.django_db
def test_signup_duplicate_email(client: DMRClient, user_a: User) -> None:
    """Duplicate email registration returns 409 Conflict."""
    payload = {
        "username": "different_user",
        "email": user_a.email,
        "password": "StrongPassword999!",
        "display_name": "Different Name",
    }
    response = client.post("/api/v1/auth/signup/", data=payload)
    assert response.status_code == HTTPStatus.CONFLICT


@pytest.mark.django_db
def test_signup_short_password(client: DMRClient) -> None:
    """Passwords shorter than 8 characters are rejected with 422."""
    payload = {
        "username": "shortpass",
        "email": "short@example.com",
        "password": "123",
        "display_name": "Short Pass",
    }
    response = client.post("/api/v1/auth/signup/", data=payload)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.django_db
def test_login_with_username_success(client: DMRClient, user_a: User) -> None:
    """Login with username returns 200 OK and valid RS256 tokens."""
    payload = {
        "email_or_username": "alice",
        "password": "AliceSecurePassword123!",
    }
    response = client.post("/api/v1/auth/login/", data=payload)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["user"]["username"] == "alice"
    assert data["profile_id"] == str(user_a.profile.id)
    assert "access" in data["tokens"]
    assert "refresh" in data["tokens"]

    # Verify audit log
    assert UserActionLog.objects.filter(action="LOGIN", user_profile=user_a.profile).exists()


@pytest.mark.django_db
def test_login_with_email_success(client: DMRClient, user_a: User) -> None:
    """Login with email returns 200 OK."""
    payload = {
        "email_or_username": "alice@example.com",
        "password": "AliceSecurePassword123!",
    }
    response = client.post("/api/v1/auth/login/", data=payload)
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["user"]["email"] == "alice@example.com"


@pytest.mark.django_db
def test_login_invalid_password(client: DMRClient, user_a: User) -> None:
    """Invalid password yields 401 Unauthorized."""
    payload = {
        "email_or_username": "alice",
        "password": "WrongPassword!",
    }
    response = client.post("/api/v1/auth/login/", data=payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_token_refresh_flow(client: DMRClient, user_a: User) -> None:
    """Valid refresh token issues new access token."""
    _, refresh = create_user_tokens(user_a)
    response = client.post("/api/v1/auth/token/refresh/", data={"refresh": refresh})
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert "access" in data
    assert len(data["access"]) > 20


@pytest.mark.django_db
def test_logout_revokes_token(
    client: DMRClient, user_a: User, auth_headers_a: dict[str, str]
) -> None:
    """Logout blacklists the refresh token preventing further refreshes."""
    _, refresh = create_user_tokens(user_a)

    # Logout
    logout_resp = client.post(
        "/api/v1/auth/logout/",
        data={"refresh": refresh},
        **auth_headers_a,
    )
    assert logout_resp.status_code == HTTPStatus.NO_CONTENT

    # Attempting to refresh with the revoked token must fail with 401
    refresh_resp = client.post("/api/v1/auth/token/refresh/", data={"refresh": refresh})
    assert refresh_resp.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.django_db
def test_stateless_password_reset_flow(client: DMRClient, user_a: User) -> None:
    """Test full reset flow: request -> verify -> confirm -> login with new password."""
    # 1. Request Reset
    req_resp = client.post(
        "/api/v1/auth/password/reset-request/", data={"email": "alice@example.com"}
    )
    assert req_resp.status_code == HTTPStatus.OK

    # Generate token manually to simulate email link
    uid = encode_user_id(user_a.id)
    token = password_reset_token_generator.make_token(user_a)

    # 2. Verify Token
    verify_resp = client.get(f"/api/v1/auth/password/verify-token/?uid={uid}&token={token}")
    assert verify_resp.status_code == HTTPStatus.OK
    assert verify_resp.json()["valid"] is True

    # 3. Confirm Reset with New Password
    confirm_resp = client.post(
        "/api/v1/auth/password/reset-confirm/",
        data={
            "uid": uid,
            "token": token,
            "new_password": "AliceNewPassword456!",
        },
    )
    assert confirm_resp.status_code == HTTPStatus.OK

    # 4. Old password fails
    fail_login = client.post(
        "/api/v1/auth/login/",
        data={"email_or_username": "alice", "password": "AliceSecurePassword123!"},
    )
    assert fail_login.status_code == HTTPStatus.UNAUTHORIZED

    # 5. New password succeeds
    success_login = client.post(
        "/api/v1/auth/login/",
        data={"email_or_username": "alice", "password": "AliceNewPassword456!"},
    )
    assert success_login.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_password_change_authenticated(
    client: DMRClient, user_a: User, auth_headers_a: dict[str, str]
) -> None:
    """Logged in user can change password."""
    payload = {
        "current_password": "AliceSecurePassword123!",
        "new_password": "AliceBrandNewPassword789!",
    }
    response = client.post("/api/v1/auth/password/change/", data=payload, **auth_headers_a)
    assert response.status_code == HTTPStatus.OK

    # Verify new password works
    login_resp = client.post(
        "/api/v1/auth/login/",
        data={"email_or_username": "alice", "password": "AliceBrandNewPassword789!"},
    )
    assert login_resp.status_code == HTTPStatus.OK


@pytest.mark.django_db
def test_auth_me_endpoint(client: DMRClient, user_a: User, auth_headers_a: dict[str, str]) -> None:
    """Endpoint /api/v1/auth/me/ returns authenticated user and profile UUID."""
    response = client.get("/api/v1/auth/me/", **auth_headers_a)
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["user"]["username"] == "alice"
    assert data["profile_id"] == str(user_a.profile.id)

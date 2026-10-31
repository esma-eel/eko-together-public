"""Tests for UserActionLog audit trail emissions."""

import pytest
from dmr.test import DMRClient

from services.auth_user_service.apps.accounts.models import (
    User,
    UserActionLog,
)


@pytest.mark.django_db
def test_audit_logs_captured_across_lifecycle(client: DMRClient) -> None:
    """Validate that UserActionLog captures client IP, user agent, and metadata."""
    headers = {
        "HTTP_X_FORWARDED_FOR": "198.51.100.42",
        "HTTP_USER_AGENT": "AntigravityTestClient/1.0",
    }

    # 1. Sign up
    client.post(
        "/api/v1/auth/signup/",
        data={
            "username": "audit_user",
            "email": "audit@example.com",
            "password": "AuditPassword123!",
            "display_name": "Audit User",
        },
        **headers,
    )
    user = User.objects.get(username="audit_user")
    signup_log = UserActionLog.objects.filter(action="SIGNUP", user_profile=user.profile).first()
    assert signup_log is not None
    assert signup_log.ip_address == "198.51.100.42"
    assert signup_log.user_agent == "AntigravityTestClient/1.0"
    assert signup_log.target_type == "USER"

    # 2. Login
    login_resp = client.post(
        "/api/v1/auth/login/",
        data={
            "email_or_username": "audit_user",
            "password": "AuditPassword123!",
        },
        **headers,
    )
    tokens = login_resp.json()["tokens"]
    auth_hdr = {
        "HTTP_AUTHORIZATION": f"Bearer {tokens['access']}",
        **headers,
    }
    login_log = UserActionLog.objects.filter(action="LOGIN", user_profile=user.profile).first()
    assert login_log is not None
    assert login_log.ip_address == "198.51.100.42"

    # 3. Update profile
    client.patch(
        "/api/v1/profiles/me/",
        data={"bio": "Audited bio update"},
        **auth_hdr,
    )
    profile_log = UserActionLog.objects.filter(
        action="PROFILE_UPDATE", user_profile=user.profile
    ).first()
    assert profile_log is not None

    # 4. Logout
    client.post(
        "/api/v1/auth/logout/",
        data={"refresh": tokens["refresh"]},
        **auth_hdr,
    )
    logout_log = UserActionLog.objects.filter(action="LOGOUT", user_profile=user.profile).first()
    assert logout_log is not None

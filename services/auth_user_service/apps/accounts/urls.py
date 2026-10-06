"""Routing definitions for accounts and identity endpoints.

Uses dmr.routing.Router and dmr.routing.path for high-performance prefix-matched dispatch.
"""

from __future__ import annotations

from dmr.routing import Router, path

from services.auth_user_service.apps.accounts.controllers.auth_controllers import (
    CurrentUserMeController,
    LoginController,
    LogoutController,
    PasswordChangeController,
    PasswordResetConfirmController,
    PasswordResetRequestController,
    PasswordVerifyTokenController,
    SignupController,
    TokenRefreshController,
)
from services.auth_user_service.apps.accounts.controllers.internal_controllers import (
    InternalRelationCheckController,
)
from services.auth_user_service.apps.accounts.controllers.profile_controllers import (
    FollowRequestActionController,
    FollowRequestsListController,
    MyProfileController,
    ProfileFollowController,
    ProfileFollowersController,
    ProfileFollowingController,
    ProfileUnfollowController,
    UserProfileDetailController,
)
from services.auth_user_service.apps.accounts.controllers.settings_controllers import (
    UserPrivacySettingsController,
)

api_router = Router(
    "api/",
    [
        # Authentication & Identity
        path("v1/auth/signup/", SignupController.as_view(), name="auth_signup"),
        path("v1/auth/login/", LoginController.as_view(), name="auth_login"),
        path("v1/auth/token/refresh/", TokenRefreshController.as_view(), name="auth_token_refresh"),
        path("v1/auth/logout/", LogoutController.as_view(), name="auth_logout"),
        path(
            "v1/auth/password/reset-request/",
            PasswordResetRequestController.as_view(),
            name="auth_password_reset_request",
        ),
        path(
            "v1/auth/password/verify-token/",
            PasswordVerifyTokenController.as_view(),
            name="auth_password_verify_token",
        ),
        path(
            "v1/auth/password/reset-confirm/",
            PasswordResetConfirmController.as_view(),
            name="auth_password_reset_confirm",
        ),
        path(
            "v1/auth/password/change/",
            PasswordChangeController.as_view(),
            name="auth_password_change",
        ),
        path("v1/auth/me/", CurrentUserMeController.as_view(), name="auth_me"),
        # Profiles & Social Graph
        path("v1/profiles/me/", MyProfileController.as_view(), name="profile_me"),
        path(
            "v1/profiles/me/follow-requests/",
            FollowRequestsListController.as_view(),
            name="profile_follow_requests",
        ),
        path(
            "v1/profiles/me/follow-requests/<int:relation_id>/",
            FollowRequestActionController.as_view(),
            name="profile_follow_request_action",
        ),
        path(
            "<str:profile_id>/follow/",
            ProfileFollowController.as_view(),
            name="profile_follow_compat",
        ),
        path(
            "v1/profiles/<str:profile_id>/follow/",
            ProfileFollowController.as_view(),
            name="profile_follow",
        ),
        path(
            "v1/profiles/<str:profile_id>/unfollow/",
            ProfileUnfollowController.as_view(),
            name="profile_unfollow",
        ),
        path(
            "v1/profiles/<str:profile_id>/followers/",
            ProfileFollowersController.as_view(),
            name="profile_followers",
        ),
        path(
            "v1/profiles/<str:profile_id>/following/",
            ProfileFollowingController.as_view(),
            name="profile_following",
        ),
        path(
            "v1/profiles/<str:username>/",
            UserProfileDetailController.as_view(),
            name="profile_detail",
        ),
        # Privacy Settings
        path(
            "v1/users/settings/privacy/",
            UserPrivacySettingsController.as_view(),
            name="user_privacy_settings",
        ),
    ],
)

internal_router = Router(
    "internal/",
    [
        path(
            "relations/check/",
            InternalRelationCheckController.as_view(),
            name="internal_relations_check",
        ),
    ],
)

# For backward compatibility with existing imports
auth_router = api_router
profiles_router = api_router
settings_router = api_router
all_routers = [api_router, internal_router]

"""Typed Data Transfer Objects (DTOs) for User & Auth Service.

Uses msgspec.Struct for lightning-fast JSON serialization and OpenAPI integration with DMR.
"""

from __future__ import annotations

import msgspec

# ==============================================================================
# 1. Authentication DTOs
# ==============================================================================


class UserSummaryDTO(msgspec.Struct, kw_only=True):
    id: str
    username: str
    email: str


class ProfileSummaryDTO(msgspec.Struct, kw_only=True):
    id: str
    display_name: str


class TokenPairDTO(msgspec.Struct, kw_only=True):
    access: str
    refresh: str


class SignupRequestDTO(msgspec.Struct, kw_only=True):
    username: str
    email: str
    password: str
    display_name: str


class SignupResponseDTO(msgspec.Struct, kw_only=True):
    user: UserSummaryDTO
    profile: ProfileSummaryDTO
    tokens: TokenPairDTO


class LoginRequestDTO(msgspec.Struct, kw_only=True):
    email_or_username: str
    password: str


class LoginResponseDTO(msgspec.Struct, kw_only=True):
    user: UserSummaryDTO
    profile_id: str
    tokens: TokenPairDTO


class TokenRefreshRequestDTO(msgspec.Struct, kw_only=True):
    refresh: str


class TokenRefreshResponseDTO(msgspec.Struct, kw_only=True):
    access: str


class LogoutRequestDTO(msgspec.Struct, kw_only=True):
    refresh: str


class PasswordResetRequestDTO(msgspec.Struct, kw_only=True):
    email: str


class MessageResponseDTO(msgspec.Struct, kw_only=True):
    message: str


class PasswordVerifyTokenQueryDTO(msgspec.Struct, kw_only=True):
    uid: str
    token: str


class PasswordVerifyTokenResponseDTO(msgspec.Struct, kw_only=True):
    valid: bool


class PasswordResetConfirmDTO(msgspec.Struct, kw_only=True):
    uid: str
    token: str
    new_password: str


class PasswordChangeDTO(msgspec.Struct, kw_only=True):
    current_password: str
    new_password: str


class CurrentUserResponseDTO(msgspec.Struct, kw_only=True):
    user: UserSummaryDTO
    profile_id: str


# ==============================================================================
# 2. Profiles and Social Graph DTOs
# ==============================================================================


class ProfileStatsDTO(msgspec.Struct, kw_only=True):
    followers_count: int
    following_count: int
    posts_count: int = 0


class ProfilePreferencesDTO(msgspec.Struct, kw_only=True):
    default_post_visibility: str
    default_comment_permission: str


class MyProfileResponseDTO(msgspec.Struct, kw_only=True):
    id: str
    username: str
    display_name: str
    avatar: str
    bio: str
    is_private: bool
    stats: ProfileStatsDTO
    preferences: ProfilePreferencesDTO
    created_at: str
    updated_at: str


class MyProfileUpdateDTO(msgspec.Struct, kw_only=True):
    display_name: str | None = None
    bio: str | None = None
    avatar: str | None = None
    is_private: bool | None = None


class PublicProfileResponseDTO(msgspec.Struct, kw_only=True):
    id: str
    username: str
    display_name: str
    avatar: str
    bio: str | None
    is_private: bool
    viewer_status: str
    stats: ProfileStatsDTO


class FollowResponseDTO(msgspec.Struct, kw_only=True):
    relation_id: int
    following_profile_id: str
    status: str
    created_at: str


class FollowRequestActorDTO(msgspec.Struct, kw_only=True):
    id: str
    username: str
    display_name: str
    avatar: str


class FollowRequestItemDTO(msgspec.Struct, kw_only=True):
    relation_id: int
    follower: FollowRequestActorDTO
    created_at: str


class FollowRequestsListDTO(msgspec.Struct, kw_only=True):
    count: int
    results: list[FollowRequestItemDTO]


class FollowActionRequestDTO(msgspec.Struct, kw_only=True):
    action: str  # APPROVE or REJECT


class FollowActionResponseDTO(msgspec.Struct, kw_only=True):
    relation_id: int
    status: str
    updated_at: str


class ProfileItemDTO(msgspec.Struct, kw_only=True):
    profile_id: str
    username: str
    display_name: str
    avatar: str


class ProfileListResponseDTO(msgspec.Struct, kw_only=True):
    count: int
    results: list[ProfileItemDTO]


class PaginationQueryDTO(msgspec.Struct, kw_only=True):
    page: int = 1
    page_size: int = 20


# ==============================================================================
# 3. Privacy Settings DTOs
# ==============================================================================


class PrivacySettingsDTO(msgspec.Struct, kw_only=True):
    is_private_account: bool
    default_post_visibility: str
    default_comment_permission: str


class PrivacySettingsUpdateDTO(msgspec.Struct, kw_only=True):
    is_private_account: bool | None = None
    default_post_visibility: str | None = None
    default_comment_permission: str | None = None


# ==============================================================================
# 4. Internal Inter-Service DTOs
# ==============================================================================


class InternalRelationCheckQueryDTO(msgspec.Struct, kw_only=True):
    follower_id: str
    target_id: str


class InternalRelationCheckResponseDTO(msgspec.Struct, kw_only=True):
    is_following: bool
    status: str

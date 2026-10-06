"""User Account & Privacy Settings DMR Controllers."""

from __future__ import annotations

from dmr import Body, Controller
from dmr.plugins.msgspec import MsgspecSerializer

from services.auth_user_service.apps.accounts.models import (
    CommentPermissionChoices,
    PostVisibilityChoices,
    UserProfile,
)
from services.auth_user_service.apps.accounts.schemas import (
    PrivacySettingsDTO,
    PrivacySettingsUpdateDTO,
)
from services.auth_user_service.apps.accounts.security import (
    AuthenticatedUserHttpRequest,
    RS256JWTSyncAuth,
)
from services.auth_user_service.apps.accounts.services import log_user_action
from shared.exceptions.base import ValidationException
from shared.exceptions.handlers import domain_exception_to_dmr_error


class UserPrivacySettingsController(Controller[MsgspecSerializer]):
    """Retrieve or update default authoring visibility and account privacy settings."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    def get(self) -> PrivacySettingsDTO:
        """Fetch current privacy parameters."""
        profile: UserProfile = self.request.profile
        return PrivacySettingsDTO(
            is_private_account=profile.is_private,
            default_post_visibility=profile.default_post_visibility,
            default_comment_permission=profile.default_comment_permission,
        )

    def patch(self, parsed_body: Body[PrivacySettingsUpdateDTO]) -> PrivacySettingsDTO:
        """Partially update user privacy defaults."""
        profile: UserProfile = self.request.profile
        updated = False

        if parsed_body.is_private_account is not None:
            profile.is_private = parsed_body.is_private_account
            updated = True

        if parsed_body.default_post_visibility is not None:
            val = parsed_body.default_post_visibility.strip().upper()
            if val not in PostVisibilityChoices.values:
                raise domain_exception_to_dmr_error(
                    ValidationException(
                        f"Invalid visibility '{val}'. Choose from: {PostVisibilityChoices.values}"
                    )
                )
            profile.default_post_visibility = val
            updated = True

        if parsed_body.default_comment_permission is not None:
            val = parsed_body.default_comment_permission.strip().upper()
            if val not in CommentPermissionChoices.values:
                raise domain_exception_to_dmr_error(
                    ValidationException(
                        f"Invalid comment permission '{val}'. "
                        f"Choose from: {CommentPermissionChoices.values}"
                    )
                )
            profile.default_comment_permission = val
            updated = True

        if updated:
            profile.save()
            log_user_action(
                self.request,
                action="PRIVACY_SETTINGS_UPDATE",
                user_profile=profile,
                target_type="PROFILE",
                target_id=str(profile.id),
                metadata={
                    "is_private": profile.is_private,
                    "default_post_visibility": profile.default_post_visibility,
                    "default_comment_permission": profile.default_comment_permission,
                },
            )

        return self.get()


UserPrivacySettingsUpdateController = UserPrivacySettingsController

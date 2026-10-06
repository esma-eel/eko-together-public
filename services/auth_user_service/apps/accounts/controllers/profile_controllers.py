"""Profile and Social Graph DMR Controllers.

Implements view/edit profile, privacy visibility rules, following/unfollowing,
follow requests listing and approval/rejection, and follower/following lists.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus

import msgspec
from dmr import Body, Controller, Path, Query, modify
from dmr.plugins.msgspec import MsgspecSerializer

from services.auth_user_service.apps.accounts.models import (
    RelationStatusChoices,
    UserProfile,
    UserRelation,
)
from services.auth_user_service.apps.accounts.schemas import (
    FollowActionRequestDTO,
    FollowActionResponseDTO,
    FollowRequestActorDTO,
    FollowRequestItemDTO,
    FollowRequestsListDTO,
    FollowResponseDTO,
    MyProfileResponseDTO,
    MyProfileUpdateDTO,
    PaginationQueryDTO,
    ProfileItemDTO,
    ProfileListResponseDTO,
    ProfilePreferencesDTO,
    ProfileStatsDTO,
    PublicProfileResponseDTO,
)
from services.auth_user_service.apps.accounts.security import (
    AuthenticatedUserHttpRequest,
    OptionalRS256JWTSyncAuth,
    RS256JWTSyncAuth,
)
from services.auth_user_service.apps.accounts.services import (
    follow_user_profile,
    handle_follow_request_action,
    log_user_action,
    unfollow_user_profile,
)
from shared.exceptions.base import (
    ConflictException,
    EntityNotFoundException,
    PermissionDeniedException,
    ValidationException,
)
from shared.exceptions.handlers import domain_exception_to_dmr_error


# --- Path parameter models ---
class UsernamePathDTO(msgspec.Struct, kw_only=True):
    username: str


class ProfileIdPathDTO(msgspec.Struct, kw_only=True):
    profile_id: str


class RelationIdPathDTO(msgspec.Struct, kw_only=True):
    relation_id: int


class MyProfileController(Controller[MsgspecSerializer]):
    """Retrieve or update full personal profile and settings for authenticated user."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    def get(self) -> MyProfileResponseDTO:
        """Fetch own profile, relationship statistics, and authoring preferences."""
        profile: UserProfile = self.request.profile
        return MyProfileResponseDTO(
            id=str(profile.id),
            username=self.request.user.username,
            display_name=profile.display_name,
            avatar=profile.avatar,
            bio=profile.bio,
            is_private=profile.is_private,
            stats=ProfileStatsDTO(
                followers_count=profile.followers_count,
                following_count=profile.following_count,
                posts_count=0,
            ),
            preferences=ProfilePreferencesDTO(
                default_post_visibility=profile.default_post_visibility,
                default_comment_permission=profile.default_comment_permission,
            ),
            created_at=profile.created_at.isoformat(),
            updated_at=profile.updated_at.isoformat(),
        )

    def patch(self, parsed_body: Body[MyProfileUpdateDTO]) -> MyProfileResponseDTO:
        """Partially update display name, avatar, bio, or private account toggle."""
        profile: UserProfile = self.request.profile
        updated = False

        if parsed_body.display_name is not None:
            profile.display_name = parsed_body.display_name.strip()
            updated = True
        if parsed_body.bio is not None:
            profile.bio = parsed_body.bio
            updated = True
        if parsed_body.avatar is not None:
            profile.avatar = parsed_body.avatar.strip()
            updated = True
        if parsed_body.is_private is not None:
            profile.is_private = parsed_body.is_private
            updated = True

        if updated:
            profile.save()
            log_user_action(
                self.request,
                action="PROFILE_UPDATE",
                user_profile=profile,
                target_type="PROFILE",
                target_id=str(profile.id),
            )

        return self.get()


MyProfileUpdateController = MyProfileController


class UserProfileDetailController(Controller[MsgspecSerializer]):
    """View someone else's public/private profile with dynamic relationship status."""

    auth = (OptionalRS256JWTSyncAuth(),)

    def get(self, parsed_path: Path[UsernamePathDTO]) -> PublicProfileResponseDTO:
        """Retrieve public or privacy-filtered profile view for target username."""
        username = parsed_path.username.strip()
        target_profile = (
            UserProfile.objects.filter(user__username__iexact=username, user__is_active=True)
            .select_related("user")
            .first()
        )
        if not target_profile:
            raise domain_exception_to_dmr_error(
                EntityNotFoundException(f"Profile for user '{username}' was not found.")
            )

        viewer_profile: UserProfile | None = getattr(self.request, "profile", None)

        # Check self
        if viewer_profile and viewer_profile.id == target_profile.id:
            viewer_status = "SELF"
            bio = target_profile.bio
        elif viewer_profile:
            rel = UserRelation.objects.filter(
                follower_profile=viewer_profile,
                following_profile=target_profile,
            ).first()
            if rel:
                viewer_status = rel.status
            else:
                viewer_status = "NONE"

            # If private account and viewer is not accepted follower: hide bio
            if target_profile.is_private and viewer_status != RelationStatusChoices.ACCEPTED:
                bio = None
            else:
                bio = target_profile.bio
        else:
            viewer_status = "NONE"
            bio = None if target_profile.is_private else target_profile.bio

        return PublicProfileResponseDTO(
            id=str(target_profile.id),
            username=target_profile.user.username,
            display_name=target_profile.display_name,
            avatar=target_profile.avatar,
            bio=bio,
            is_private=target_profile.is_private,
            viewer_status=viewer_status,
            stats=ProfileStatsDTO(
                followers_count=target_profile.followers_count,
                following_count=target_profile.following_count,
                posts_count=0,
            ),
        )


class ProfileFollowController(Controller[MsgspecSerializer]):
    """Follow a user or create a pending follow request for private profile."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    @modify(status_code=HTTPStatus.CREATED)
    def post(self, parsed_path: Path[ProfileIdPathDTO]) -> FollowResponseDTO:
        """Create follow relation edge."""
        try:
            target_uuid = uuid.UUID(parsed_path.profile_id)
        except ValueError as exc:
            raise domain_exception_to_dmr_error(
                ValidationException("Invalid profile UUID format.")
            ) from exc

        target_profile = (
            UserProfile.objects.filter(id=target_uuid, user__is_active=True)
            .select_related("user")
            .first()
        )
        if not target_profile:
            raise domain_exception_to_dmr_error(
                EntityNotFoundException("Target user profile was not found.")
            )

        try:
            relation = follow_user_profile(
                follower=self.request.profile,
                target=target_profile,
            )
        except (ConflictException, ValidationException) as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        action_name = (
            "FOLLOW_REQUEST" if relation.status == RelationStatusChoices.PENDING else "FOLLOW"
        )
        log_user_action(
            self.request,
            action=action_name,
            user_profile=self.request.profile,
            target_type="PROFILE",
            target_id=str(target_profile.id),
            metadata={"relation_id": relation.id, "status": relation.status},
        )

        return FollowResponseDTO(
            relation_id=relation.id,
            following_profile_id=str(target_profile.id),
            status=relation.status,
            created_at=relation.created_at.isoformat(),
        )


class ProfileUnfollowController(Controller[MsgspecSerializer]):
    """Unfollow a user or cancel an existing pending follow request."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    @modify(status_code=HTTPStatus.NO_CONTENT)
    def delete(self, parsed_path: Path[ProfileIdPathDTO]) -> None:
        """Remove follow edge between authenticated user and target."""
        try:
            target_uuid = uuid.UUID(parsed_path.profile_id)
        except ValueError as exc:
            raise domain_exception_to_dmr_error(
                ValidationException("Invalid profile UUID format.")
            ) from exc

        target_profile = UserProfile.objects.filter(id=target_uuid).first()
        if not target_profile:
            raise domain_exception_to_dmr_error(
                EntityNotFoundException("Target user profile was not found.")
            )

        try:
            unfollow_user_profile(
                follower=self.request.profile,
                target=target_profile,
            )
        except (EntityNotFoundException, ValidationException) as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        log_user_action(
            self.request,
            action="UNFOLLOW",
            user_profile=self.request.profile,
            target_type="PROFILE",
            target_id=str(target_profile.id),
        )


class FollowRequestsListController(Controller[MsgspecSerializer]):
    """List inbound pending follow requests for the authenticated user."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    def get(self) -> FollowRequestsListDTO:
        """Fetch all pending follow requests awaiting decision."""
        requests_qs = (
            UserRelation.objects.filter(
                following_profile=self.request.profile,
                status=RelationStatusChoices.PENDING,
            )
            .select_related("follower_profile__user")
            .order_by("-created_at")
        )

        results = [
            FollowRequestItemDTO(
                relation_id=rel.id,
                follower=FollowRequestActorDTO(
                    id=str(rel.follower_profile.id),
                    username=rel.follower_profile.user.username,
                    display_name=rel.follower_profile.display_name,
                    avatar=rel.follower_profile.avatar,
                ),
                created_at=rel.created_at.isoformat(),
            )
            for rel in requests_qs
        ]

        return FollowRequestsListDTO(count=len(results), results=results)


class FollowRequestActionController(Controller[MsgspecSerializer]):
    """Approve or reject a pending follow request."""

    request: AuthenticatedUserHttpRequest
    auth = (RS256JWTSyncAuth(),)

    @modify(status_code=HTTPStatus.OK)
    def post(
        self,
        parsed_path: Path[RelationIdPathDTO],
        parsed_body: Body[FollowActionRequestDTO],
    ) -> FollowActionResponseDTO:
        """Perform APPROVE or REJECT on designated follow request."""
        try:
            relation = handle_follow_request_action(
                owner=self.request.profile,
                relation_id=parsed_path.relation_id,
                action=parsed_body.action,
            )
        except (EntityNotFoundException, ValidationException) as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        action_name = f"FOLLOW_{parsed_body.action.strip().upper()}"
        log_user_action(
            self.request,
            action=action_name,
            user_profile=self.request.profile,
            target_type="RELATION",
            target_id=str(relation.id),
            metadata={"status": relation.status},
        )

        return FollowActionResponseDTO(
            relation_id=relation.id,
            status=relation.status,
            updated_at=relation.updated_at.isoformat(),
        )


class ProfileFollowersController(Controller[MsgspecSerializer]):
    """List accepted followers for a given profile."""

    auth = (OptionalRS256JWTSyncAuth(),)

    def get(
        self,
        parsed_path: Path[ProfileIdPathDTO],
        parsed_query: Query[PaginationQueryDTO],
    ) -> ProfileListResponseDTO:
        """Fetch paginated list of accepted followers respecting privacy policy."""
        try:
            target_uuid = uuid.UUID(parsed_path.profile_id)
        except ValueError as exc:
            raise domain_exception_to_dmr_error(
                ValidationException("Invalid profile UUID format.")
            ) from exc

        target_profile = (
            UserProfile.objects.filter(id=target_uuid, user__is_active=True)
            .select_related("user")
            .first()
        )
        if not target_profile:
            raise domain_exception_to_dmr_error(
                EntityNotFoundException("Target user profile was not found.")
            )

        viewer_profile: UserProfile | None = getattr(self.request, "profile", None)

        # Check privacy access: if private, viewer must be owner or accepted follower
        if target_profile.is_private:
            if not viewer_profile:
                raise domain_exception_to_dmr_error(
                    PermissionDeniedException(
                        "This account is private. Log in and follow to view followers."
                    )
                )
            if viewer_profile.id != target_profile.id:
                is_follower = UserRelation.objects.filter(
                    follower_profile=viewer_profile,
                    following_profile=target_profile,
                    status=RelationStatusChoices.ACCEPTED,
                ).exists()
                if not is_follower:
                    raise domain_exception_to_dmr_error(
                        PermissionDeniedException(
                            "This account is private. Only approved followers may view."
                        )
                    )

        qs = (
            UserRelation.objects.filter(
                following_profile=target_profile,
                status=RelationStatusChoices.ACCEPTED,
                follower_profile__user__is_active=True,
            )
            .select_related("follower_profile__user")
            .order_by("-created_at")
        )

        total_count = qs.count()
        offset = (max(parsed_query.page, 1) - 1) * parsed_query.page_size
        items = qs[offset : offset + parsed_query.page_size]

        results = [
            ProfileItemDTO(
                profile_id=str(rel.follower_profile.id),
                username=rel.follower_profile.user.username,
                display_name=rel.follower_profile.display_name,
                avatar=rel.follower_profile.avatar,
            )
            for rel in items
        ]

        return ProfileListResponseDTO(count=total_count, results=results)


class ProfileFollowingController(Controller[MsgspecSerializer]):
    """List accounts that a given profile is actively following."""

    auth = (OptionalRS256JWTSyncAuth(),)

    def get(
        self,
        parsed_path: Path[ProfileIdPathDTO],
        parsed_query: Query[PaginationQueryDTO],
    ) -> ProfileListResponseDTO:
        """Fetch paginated list of accounts followed by target respecting privacy policy."""
        try:
            target_uuid = uuid.UUID(parsed_path.profile_id)
        except ValueError as exc:
            raise domain_exception_to_dmr_error(
                ValidationException("Invalid profile UUID format.")
            ) from exc

        target_profile = (
            UserProfile.objects.filter(id=target_uuid, user__is_active=True)
            .select_related("user")
            .first()
        )
        if not target_profile:
            raise domain_exception_to_dmr_error(
                EntityNotFoundException("Target user profile was not found.")
            )

        viewer_profile: UserProfile | None = getattr(self.request, "profile", None)

        if target_profile.is_private:
            if not viewer_profile:
                raise domain_exception_to_dmr_error(
                    PermissionDeniedException(
                        "This account is private. Log in and follow to view following."
                    )
                )
            if viewer_profile.id != target_profile.id:
                is_follower = UserRelation.objects.filter(
                    follower_profile=viewer_profile,
                    following_profile=target_profile,
                    status=RelationStatusChoices.ACCEPTED,
                ).exists()
                if not is_follower:
                    raise domain_exception_to_dmr_error(
                        PermissionDeniedException(
                            "This account is private. Only approved followers may view."
                        )
                    )

        qs = (
            UserRelation.objects.filter(
                follower_profile=target_profile,
                status=RelationStatusChoices.ACCEPTED,
                following_profile__user__is_active=True,
            )
            .select_related("following_profile__user")
            .order_by("-created_at")
        )

        total_count = qs.count()
        offset = (max(parsed_query.page, 1) - 1) * parsed_query.page_size
        items = qs[offset : offset + parsed_query.page_size]

        results = [
            ProfileItemDTO(
                profile_id=str(rel.following_profile.id),
                username=rel.following_profile.user.username,
                display_name=rel.following_profile.display_name,
                avatar=rel.following_profile.avatar,
            )
            for rel in items
        ]

        return ProfileListResponseDTO(count=total_count, results=results)

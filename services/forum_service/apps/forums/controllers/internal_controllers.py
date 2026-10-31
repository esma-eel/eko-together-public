"""Internal service-to-service controllers for inter-service communication."""

from __future__ import annotations

from uuid import UUID

from dmr import Controller, Path, Query
from dmr.plugins.msgspec import MsgspecSerializer

from services.forum_service.apps.forums.schemas import (
    CheckPostPermissionResponseSchema,
    InternalForumPathSchema,
    InternalPermissionQuerySchema,
)
from services.forum_service.apps.forums.services import (
    check_post_permission,
    get_forum_by_id,
)
from shared.exceptions.base import DomainException, ValidationException
from shared.exceptions.handlers import domain_exception_to_dmr_error


class ForumInternalPermissionController(Controller[MsgspecSerializer]):
    """Internal API endpoint for Post & Comment service to verify posting permissions."""

    def get(
        self,
        parsed_path: Path[InternalForumPathSchema],
        parsed_query: Query[InternalPermissionQuerySchema],
    ) -> CheckPostPermissionResponseSchema:
        """Evaluate if user is permitted to post in this forum without coupling database schemas."""
        try:
            try:
                forum_uuid = UUID(parsed_path.forum_id)
            except ValueError as err:
                raise ValidationException("Invalid forum_id format. Must be a valid UUID.") from err

            try:
                user_uuid = UUID(parsed_query.user_profile_id)
            except ValueError as err:
                msg = "Invalid user_profile_id format. Must be a valid UUID."
                raise ValidationException(msg) from err

            forum = get_forum_by_id(forum_uuid)
            can_post, user_role, user_status, reason = check_post_permission(
                forum=forum,
                user_profile_id=user_uuid,
                admin_visibility=parsed_query.admin_visibility,
            )

            return CheckPostPermissionResponseSchema(
                can_post=can_post,
                forum_id=str(forum.id),
                post_permission=forum.post_permission,
                is_comments_locked=forum.is_comments_locked,
                user_role=user_role,
                user_status=user_status,
                reason=reason,
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

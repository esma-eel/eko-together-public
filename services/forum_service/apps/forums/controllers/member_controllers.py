"""Controllers for Forum membership, subscriptions, and member moderation."""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from dmr import Body, Controller, Path, Query, modify
from dmr.plugins.msgspec import MsgspecSerializer

from services.forum_service.apps.forums.models import ForumMember
from services.forum_service.apps.forums.schemas import (
    ForumMemberItemSchema,
    ForumMemberListQuerySchema,
    ForumMemberListResponseSchema,
    ForumMemberPathSchema,
    ForumSlugPathSchema,
    JoinForumResponseSchema,
    UpdateMemberRoleStatusSchema,
)
from services.forum_service.apps.forums.security import (
    AuthenticatedForumHttpRequest,
    RS256JWTSyncAuth,
)
from services.forum_service.apps.forums.services import (
    get_forum_by_slug,
    join_or_apply_forum,
    kick_member,
    leave_forum,
    update_member_role_or_status,
)
from shared.exceptions.base import DomainException, ValidationException
from shared.exceptions.handlers import domain_exception_to_dmr_error


def serialize_member(member: ForumMember) -> ForumMemberItemSchema:
    """Helper to convert a ForumMember model to ForumMemberItemSchema."""
    return ForumMemberItemSchema(
        id=member.id,
        forum_id=str(member.forum_id),
        user_profile_id=str(member.user_profile_id),
        role=member.role,
        status=member.status,
        joined_at=member.joined_at.isoformat(),
    )


class ForumMemberListController(Controller[MsgspecSerializer]):
    """List subscribers and filter membership states in a forum."""

    def get(
        self,
        parsed_path: Path[ForumSlugPathSchema],
        parsed_query: Query[ForumMemberListQuerySchema],
    ) -> ForumMemberListResponseSchema:
        """Retrieve paginated list of forum members filtered by role and status."""
        try:
            forum = get_forum_by_slug(parsed_path.slug)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        qs = ForumMember.objects.filter(forum=forum).order_by("joined_at")

        if parsed_query.role:
            qs = qs.filter(role=parsed_query.role)
        if parsed_query.status:
            qs = qs.filter(status=parsed_query.status)

        count = qs.count()
        page = max(1, parsed_query.page)
        page_size = min(100, max(1, parsed_query.page_size))
        start = (page - 1) * page_size
        results = [serialize_member(m) for m in qs[start : start + page_size]]

        return ForumMemberListResponseSchema(count=count, results=results)


class ForumJoinController(Controller[MsgspecSerializer]):
    """Join or apply for membership in a forum."""

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.CREATED)
    def post(self, parsed_path: Path[ForumSlugPathSchema]) -> JoinForumResponseSchema:
        """Submit membership subscription or join request."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        try:
            forum = get_forum_by_slug(parsed_path.slug)
            status, message = join_or_apply_forum(
                forum=forum,
                user_profile_id=request.claims.profile_id,
            )
            return JoinForumResponseSchema(status=status, message=message)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class ForumLeaveController(Controller[MsgspecSerializer]):
    """Leave a forum subscription."""

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.NO_CONTENT)
    def post(self, parsed_path: Path[ForumSlugPathSchema]) -> None:
        """Unsubscribe from the forum."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        try:
            forum = get_forum_by_slug(parsed_path.slug)
            leave_forum(forum=forum, user_profile_id=request.claims.profile_id)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class ForumMemberDetailController(Controller[MsgspecSerializer]):
    """Moderate an individual forum member (promote, approve, ban, or kick)."""

    auth = (RS256JWTSyncAuth(),)

    def patch(
        self,
        parsed_path: Path[ForumMemberPathSchema],
        parsed_body: Body[UpdateMemberRoleStatusSchema],
    ) -> ForumMemberItemSchema:
        """Promote, demote, approve, or ban a forum member."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        try:
            try:
                target_uuid = UUID(parsed_path.user_profile_id)
            except ValueError as err:
                msg = "Invalid user_profile_id format. Must be a valid UUID."
                raise ValidationException(msg) from err

            forum = get_forum_by_slug(parsed_path.slug)
            member = update_member_role_or_status(
                forum=forum,
                operator_profile_id=request.claims.profile_id,
                target_profile_id=target_uuid,
                role=parsed_body.role,
                status=parsed_body.status,
            )
            return serialize_member(member)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(status_code=HTTPStatus.NO_CONTENT)
    def delete(self, parsed_path: Path[ForumMemberPathSchema]) -> None:
        """Kick or remove a member from the forum."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        try:
            try:
                target_uuid = UUID(parsed_path.user_profile_id)
            except ValueError as err:
                msg = "Invalid user_profile_id format. Must be a valid UUID."
                raise ValidationException(msg) from err

            forum = get_forum_by_slug(parsed_path.slug)
            kick_member(
                forum=forum,
                operator_profile_id=request.claims.profile_id,
                target_profile_id=target_uuid,
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

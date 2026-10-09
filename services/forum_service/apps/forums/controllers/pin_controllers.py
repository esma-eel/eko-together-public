"""Controllers for forum-level pinned posts and quota enforcement."""

from __future__ import annotations

from uuid import UUID

from dmr import Body, Controller, Path
from dmr.plugins.msgspec import MsgspecSerializer

from services.forum_service.apps.forums.models import ForumPinnedPost
from services.forum_service.apps.forums.schemas import (
    ForumPostPinPathSchema,
    ForumSlugPathSchema,
    PinnedPostItemSchema,
    PinnedPostListResponseSchema,
    PinPostRequestSchema,
    PinPostResponseSchema,
)
from services.forum_service.apps.forums.security import (
    AuthenticatedForumHttpRequest,
    RS256JWTSyncAuth,
)
from services.forum_service.apps.forums.services import (
    get_forum_by_slug,
    pin_or_unpin_post,
)
from shared.exceptions.base import DomainException, ValidationException
from shared.exceptions.handlers import domain_exception_to_dmr_error


class ForumPinPostController(Controller[MsgspecSerializer]):
    """Pin or unpin a post in a forum with max-10 quota enforcement."""

    auth = (RS256JWTSyncAuth(),)

    def patch(
        self,
        parsed_path: Path[ForumPostPinPathSchema],
        parsed_body: Body[PinPostRequestSchema],
    ) -> PinPostResponseSchema:
        """Pin or unpin a post within the forum. Restricted to Owner or Admin."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        try:
            try:
                post_uuid = UUID(parsed_path.post_id)
            except ValueError as err:
                raise ValidationException("Invalid post_id format. Must be a valid UUID.") from err

            forum = get_forum_by_slug(parsed_path.slug)
            p_id, is_pinned, pin_order, active_pins_count = pin_or_unpin_post(
                forum=forum,
                operator_profile_id=request.claims.profile_id,
                post_id=post_uuid,
                is_pinned=parsed_body.is_pinned,
                pin_order=parsed_body.pin_order,
            )

            return PinPostResponseSchema(
                post_id=str(p_id),
                forum_id=str(forum.id),
                is_pinned=is_pinned,
                pin_order=pin_order,
                active_pins_count=active_pins_count,
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class ForumPinnedPostListController(Controller[MsgspecSerializer]):
    """List all currently active pinned posts in a forum."""

    def get(self, parsed_path: Path[ForumSlugPathSchema]) -> PinnedPostListResponseSchema:
        """Retrieve list of active pinned posts ordered by pin_order."""
        try:
            forum = get_forum_by_slug(parsed_path.slug)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        pins = ForumPinnedPost.objects.filter(
            forum=forum,
            is_pinned=True,
        ).order_by("pin_order", "-created_at")

        results = [
            PinnedPostItemSchema(
                id=p.id,
                post_id=str(p.post_id),
                pin_order=p.pin_order,
                is_pinned=p.is_pinned,
                pinned_by_profile_id=str(p.pinned_by_profile_id),
                created_at=p.created_at.isoformat(),
            )
            for p in pins
        ]

        return PinnedPostListResponseSchema(count=len(results), results=results)

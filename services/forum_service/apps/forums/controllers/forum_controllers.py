"""Controllers for Forum CRUD, discovery, and community management."""

from __future__ import annotations

from http import HTTPStatus

from django.db.models import Q
from dmr import Body, Controller, Path, Query, modify
from dmr.plugins.msgspec import MsgspecSerializer

from services.forum_service.apps.forums.models import Forum, ForumMember, MemberStatusChoices
from services.forum_service.apps.forums.schemas import (
    ForumCreateSchema,
    ForumDetailResponseSchema,
    ForumFilterQuerySchema,
    ForumListResponseSchema,
    ForumResponseSchema,
    ForumSlugPathSchema,
    ForumUpdateSchema,
)
from services.forum_service.apps.forums.security import (
    AuthenticatedForumHttpRequest,
    OptionalRS256JWTSyncAuth,
    RS256JWTSyncAuth,
)
from services.forum_service.apps.forums.services import (
    create_forum,
    delete_forum,
    get_forum_by_slug,
    update_forum,
)
from shared.exceptions.base import AuthenticationFailedException, DomainException
from shared.exceptions.handlers import domain_exception_to_dmr_error


def serialize_forum(forum: Forum) -> ForumResponseSchema:
    """Helper to convert a Forum model to ForumResponseSchema."""
    return ForumResponseSchema(
        id=str(forum.id),
        title=forum.title,
        slug=forum.slug,
        description=forum.description,
        rules=forum.rules,
        avatar=forum.avatar,
        cover_image=forum.cover_image,
        require_approval_to_join=forum.require_approval_to_join,
        post_permission=forum.post_permission,
        is_comments_locked=forum.is_comments_locked,
        owner_profile_id=str(forum.owner_profile_id),
        members_count=forum.members_count,
        created_at=forum.created_at.isoformat(),
        updated_at=forum.updated_at.isoformat(),
    )


class ForumListCreateController(Controller[MsgspecSerializer]):
    """Public discovery and authenticated creation of sub-community forums."""

    def get(self, parsed_query: Query[ForumFilterQuerySchema]) -> ForumListResponseSchema:
        """Browse or search sub-communities with pagination."""
        qs = Forum.objects.all().order_by("-created_at")

        if parsed_query.search:
            term = parsed_query.search.strip()
            qs = qs.filter(
                Q(title__icontains=term) | Q(description__icontains=term) | Q(slug__icontains=term)
            )

        count = qs.count()
        page = max(1, parsed_query.page)
        page_size = min(100, max(1, parsed_query.page_size))
        start = (page - 1) * page_size
        results = [serialize_forum(f) for f in qs[start : start + page_size]]

        return ForumListResponseSchema(count=count, results=results)

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.CREATED)
    def post(self, parsed_body: Body[ForumCreateSchema]) -> ForumResponseSchema:
        """Create a new forum community. Requester automatically becomes OWNER."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )
        try:
            forum = create_forum(
                owner_profile_id=request.claims.profile_id,
                payload=parsed_body,
            )
            return serialize_forum(forum)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class ForumDetailController(Controller[MsgspecSerializer]):
    """Retrieve, update, or delete a specific forum by slug."""

    @modify(auth=(OptionalRS256JWTSyncAuth(),))
    def get(self, parsed_path: Path[ForumSlugPathSchema]) -> ForumDetailResponseSchema:
        """Retrieve forum metadata, rules, and optional membership status."""
        try:
            forum = get_forum_by_slug(parsed_path.slug)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        is_member = False
        my_role = None
        my_status = None

        claims = getattr(self.request, "claims", None)
        if claims:
            membership = ForumMember.objects.filter(
                forum=forum,
                user_profile_id=claims.profile_id,
            ).first()
            if membership:
                is_member = membership.status == MemberStatusChoices.APPROVED
                my_role = membership.role
                my_status = membership.status

        return ForumDetailResponseSchema(
            id=str(forum.id),
            title=forum.title,
            slug=forum.slug,
            description=forum.description,
            rules=forum.rules,
            avatar=forum.avatar,
            cover_image=forum.cover_image,
            require_approval_to_join=forum.require_approval_to_join,
            post_permission=forum.post_permission,
            is_comments_locked=forum.is_comments_locked,
            owner_profile_id=str(forum.owner_profile_id),
            members_count=forum.members_count,
            created_at=forum.created_at.isoformat(),
            updated_at=forum.updated_at.isoformat(),
            is_member=is_member,
            my_role=my_role,
            my_status=my_status,
        )

    @modify(auth=(RS256JWTSyncAuth(),))
    def patch(
        self,
        parsed_path: Path[ForumSlugPathSchema],
        parsed_body: Body[ForumUpdateSchema],
    ) -> ForumResponseSchema:
        """Update forum configuration or policy. Restricted to Owner or Admin."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )
        try:
            forum = get_forum_by_slug(parsed_path.slug)
            updated = update_forum(
                forum=forum,
                operator_profile_id=request.claims.profile_id,
                payload=parsed_body,
            )
            return serialize_forum(updated)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.NO_CONTENT)
    def delete(self, parsed_path: Path[ForumSlugPathSchema]) -> None:
        """Permanently delete a forum community. Restricted strictly to Owner."""
        request: AuthenticatedForumHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )
        try:
            forum = get_forum_by_slug(parsed_path.slug)
            delete_forum(forum=forum, operator_profile_id=request.claims.profile_id)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

"""DMR Controllers for Post & Comment Service - Posts module.

Skinny Controllers following django-modern-rest patterns:
- Component parameters named parsed_path, parsed_query, parsed_body.
- Authentication claims extraction and delegation of domain logic to services layer.
- Responses serialized to msgspec Struct models.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from uuid import UUID

from dmr import Body, Controller, Path, Query, modify
from dmr.plugins.msgspec import MsgspecSerializer

from services.post_comment_service.apps.posts import schemas, services
from services.post_comment_service.apps.posts.security import (
    AuthenticatedPostHttpRequest,
    OptionalRS256JWTSyncAuth,
    RS256JWTSyncAuth,
)
from shared.exceptions.base import (
    AuthenticationFailedException,
    DomainException,
)
from shared.exceptions.handlers import domain_exception_to_dmr_error


def serialize_post(doc: dict[str, Any]) -> schemas.PostResponseSchema:
    """Helper to convert a post document dictionary into PostResponseSchema."""
    return schemas.PostResponseSchema(
        **{
            **doc,
            "tags": [
                schemas.TagSchema(name=t["name"], slug=t["slug"]) for t in doc.get("tags", [])
            ],
        }
    )


# ============================================================================
# POST LIST + CREATE: GET /api/v1/posts/  POST /api/v1/posts/
# ============================================================================


class PostListCreateController(Controller[MsgspecSerializer]):
    """List posts or create a new post.

    GET  /api/v1/posts/ — public list with filtering
    POST /api/v1/posts/ — create a post (auth required)
    """

    @modify(auth=(OptionalRS256JWTSyncAuth(),))
    def get(
        self,
        parsed_query: Query[schemas.PostListQuerySchema],
    ) -> schemas.PostListResponseSchema:
        """List posts with optional filtering by forum, author, and tag."""
        claims = getattr(self.request, "claims", None)
        viewer_profile_id: UUID | None = claims.profile_id if claims else None

        try:
            results, total = services.list_posts(parsed_query, viewer_profile_id)
            return schemas.PostListResponseSchema(
                count=total,
                next_cursor=None,
                results=[serialize_post(r) for r in results],
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.CREATED)
    def post(
        self,
        parsed_body: Body[schemas.PostCreateSchema],
    ) -> schemas.PostResponseSchema:
        """Create a new post. Requester profile is resolved from JWT claims."""
        request: AuthenticatedPostHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        try:
            doc = services.create_post(request.claims.profile_id, parsed_body)
            return serialize_post(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# POST DETAIL: GET/PATCH/DELETE /api/v1/posts/{post_id}/
# ============================================================================


class PostDetailController(Controller[MsgspecSerializer]):
    """Retrieve, update, or delete a single post.

    GET    /api/v1/posts/{post_id}/ — retrieve (optional auth)
    PATCH  /api/v1/posts/{post_id}/ — update (auth required)
    DELETE /api/v1/posts/{post_id}/ — soft-delete (auth required)
    """

    @modify(auth=(OptionalRS256JWTSyncAuth(),))
    def get(
        self,
        parsed_path: Path[schemas.PostIdPathSchema],
    ) -> schemas.PostResponseSchema:
        """Retrieve a single post by ID."""
        claims = getattr(self.request, "claims", None)
        viewer_profile_id: UUID | None = claims.profile_id if claims else None

        try:
            doc = services.get_post(parsed_path.post_id, viewer_profile_id)
            return serialize_post(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(auth=(RS256JWTSyncAuth(),))
    def patch(
        self,
        parsed_path: Path[schemas.PostIdPathSchema],
        parsed_body: Body[schemas.PostUpdateSchema],
    ) -> schemas.PostResponseSchema:
        """Update post content or settings. Permissions evaluated by service."""
        request: AuthenticatedPostHttpRequest = self.request  # type: ignore[assignment]
        try:
            updated = services.update_post(
                parsed_path.post_id,
                request.claims.profile_id,
                parsed_body,
            )
            return serialize_post(updated)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.NO_CONTENT)
    def delete(
        self,
        parsed_path: Path[schemas.PostIdPathSchema],
    ) -> None:
        """Soft-delete a post. Permissions evaluated by service."""
        request: AuthenticatedPostHttpRequest = self.request  # type: ignore[assignment]
        try:
            services.delete_post(parsed_path.post_id, request.claims.profile_id)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# POST ARCHIVE: POST /api/v1/posts/{post_id}/archive/
# ============================================================================


class PostArchiveController(Controller[MsgspecSerializer]):
    """Toggle archive state for a post.

    POST /api/v1/posts/{post_id}/archive/
    """

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.OK)
    def post(
        self,
        parsed_path: Path[schemas.PostIdPathSchema],
        parsed_body: Body[schemas.ArchivePostSchema],
    ) -> schemas.PostArchiveResponseSchema:
        """Archive or unarchive a post."""
        request: AuthenticatedPostHttpRequest = self.request  # type: ignore[assignment]
        try:
            result = services.toggle_archive_post(
                parsed_path.post_id,
                request.claims.profile_id,
                parsed_body.is_archived,
            )
            return schemas.PostArchiveResponseSchema(**result)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# POST PIN: POST /api/v1/posts/{post_id}/pin/
# ============================================================================


class PostPinController(Controller[MsgspecSerializer]):
    """Pin or unpin a post in its forum.

    POST /api/v1/posts/{post_id}/pin/
    """

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.OK)
    def post(
        self,
        parsed_path: Path[schemas.PostIdPathSchema],
        parsed_body: Body[schemas.PinPostSchema],
    ) -> schemas.PostPinResponseSchema:
        """Pin or unpin a post within a forum."""
        request: AuthenticatedPostHttpRequest = self.request  # type: ignore[assignment]
        try:
            result = services.pin_post(
                parsed_path.post_id,
                request.claims.profile_id,
                parsed_body.is_pinned,
                parsed_body.pin_order,
            )
            return schemas.PostPinResponseSchema(**result)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

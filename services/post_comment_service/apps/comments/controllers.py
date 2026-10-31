"""DMR Controllers for Post & Comment Service - Comments module.

Controllers:
  - CommentListCreateController : GET/POST /api/v1/posts/{post_id}/comments/
  - CommentReplyController      : POST /api/v1/comments/{comment_id}/replies/
  - CommentDetailController     : GET/PATCH/DELETE /api/v1/comments/{comment_id}/
  - CommentArchiveController    : POST /api/v1/comments/{comment_id}/archive/
  - CommentVoteController       : POST /api/v1/comments/{comment_id}/vote/
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any
from uuid import UUID

from dmr import Body, Controller, Path, Query, modify
from dmr.plugins.msgspec import MsgspecSerializer

from services.post_comment_service.apps.comments import schemas, services
from services.post_comment_service.apps.comments.security import (
    AuthenticatedCommentHttpRequest,
    OptionalRS256JWTSyncAuth,
    RS256JWTSyncAuth,
)
from shared.exceptions.base import (
    AuthenticationFailedException,
    DomainException,
)
from shared.exceptions.handlers import domain_exception_to_dmr_error


def serialize_comment(d: dict[str, Any]) -> schemas.CommentResponseSchema:
    """Recursively convert a comment document dict into CommentResponseSchema."""
    return schemas.CommentResponseSchema(
        id=d["id"],
        post_id=d["post_id"],
        parent_id=d.get("parent_id"),
        depth=d["depth"],
        author=schemas.AuthorMiniSchema(
            id=d["author"]["id"],
            display_name=d["author"]["display_name"],
            avatar=d["author"]["avatar"],
        ),
        body=d["body"],
        upvotes_count=d["upvotes_count"],
        downvotes_count=d["downvotes_count"],
        popularity_score=d["popularity_score"],
        user_vote=d.get("user_vote"),
        is_archived=d["is_archived"],
        is_deleted=d["is_deleted"],
        replies_count=d["replies_count"],
        replies=[serialize_comment(r) for r in d.get("replies", [])],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )


# ============================================================================
# COMMENTS ON A POST: GET/POST /api/v1/posts/{post_id}/comments/
# ============================================================================


class CommentListCreateController(Controller[MsgspecSerializer]):
    """List root comments on a post, or submit a new root comment.

    GET  /api/v1/posts/{post_id}/comments/ — paginated list (optional auth)
    POST /api/v1/posts/{post_id}/comments/ — create root comment (auth required)
    """

    @modify(auth=(OptionalRS256JWTSyncAuth(),))
    def get(
        self,
        parsed_path: Path[schemas.PostCommentPathSchema],
        parsed_query: Query[schemas.CommentListQuerySchema],
    ) -> schemas.CommentListResponseSchema:
        """Return root-level comments with nested first-level replies inline."""
        claims = getattr(self.request, "claims", None)
        viewer_profile_id: UUID | None = claims.profile_id if claims else None

        try:
            results, total = services.list_comments(
                post_id=parsed_path.post_id,
                ordering=parsed_query.ordering,
                page=parsed_query.page,
                page_size=parsed_query.page_size,
                viewer_profile_id=viewer_profile_id,
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

        has_next = (parsed_query.page * parsed_query.page_size) < total
        next_url = (
            f"/api/v1/posts/{parsed_path.post_id}/comments/"
            f"?ordering={parsed_query.ordering}&page={parsed_query.page + 1}"
            f"&page_size={parsed_query.page_size}"
            if has_next
            else None
        )
        prev_url = (
            f"/api/v1/posts/{parsed_path.post_id}/comments/"
            f"?ordering={parsed_query.ordering}&page={parsed_query.page - 1}"
            f"&page_size={parsed_query.page_size}"
            if parsed_query.page > 1
            else None
        )

        return schemas.CommentListResponseSchema(
            count=total,
            next=next_url,
            previous=prev_url,
            results=[serialize_comment(d) for d in results],
        )

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.CREATED)
    def post(
        self,
        parsed_path: Path[schemas.PostCommentPathSchema],
        parsed_body: Body[schemas.CommentCreateSchema],
    ) -> schemas.CommentResponseSchema:
        """Create a root comment (depth=0) on a post."""
        request: AuthenticatedCommentHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        try:
            doc = services.create_root_comment(
                post_id=parsed_path.post_id,
                author_profile_id=request.claims.profile_id,
                body=parsed_body.body,
                author_display_name=request.claims.username,
            )
            return serialize_comment(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# REPLY TO COMMENT: POST /api/v1/comments/{comment_id}/replies/
# ============================================================================


class CommentReplyController(Controller[MsgspecSerializer]):
    """Reply to an existing comment with depth enforcement.

    POST /api/v1/comments/{comment_id}/replies/
    """

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.CREATED)
    def post(
        self,
        parsed_path: Path[schemas.CommentIdPathSchema],
        parsed_body: Body[schemas.CommentReplySchema],
    ) -> schemas.CommentResponseSchema:
        """Create a nested reply."""
        request: AuthenticatedCommentHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        try:
            doc = services.create_reply(
                parent_comment_id=parsed_path.comment_id,
                author_profile_id=request.claims.profile_id,
                body=parsed_body.body,
                author_display_name=request.claims.username,
            )
            return serialize_comment(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# COMMENT DETAIL: GET/PATCH/DELETE /api/v1/comments/{comment_id}/
# ============================================================================


class CommentDetailController(Controller[MsgspecSerializer]):
    """Retrieve, edit, or soft-delete a single comment.

    GET    /api/v1/comments/{comment_id}/ — retrieve
    PATCH  /api/v1/comments/{comment_id}/ — update body (author only)
    DELETE /api/v1/comments/{comment_id}/ — soft-delete (author or forum mod)
    """

    @modify(auth=(OptionalRS256JWTSyncAuth(),))
    def get(
        self,
        parsed_path: Path[schemas.CommentIdPathSchema],
    ) -> schemas.CommentResponseSchema:
        """Retrieve a single comment."""
        try:
            doc = services.get_comment(parsed_path.comment_id)
            return serialize_comment(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(auth=(RS256JWTSyncAuth(),))
    def patch(
        self,
        parsed_path: Path[schemas.CommentIdPathSchema],
        parsed_body: Body[schemas.CommentUpdateSchema],
    ) -> schemas.CommentResponseSchema:
        """Edit comment text. Permitted for comment author."""
        request: AuthenticatedCommentHttpRequest = self.request  # type: ignore[assignment]
        try:
            doc = services.update_comment(
                comment_id=parsed_path.comment_id,
                requester_profile_id=request.claims.profile_id,
                body=parsed_body.body,
            )
            return serialize_comment(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.NO_CONTENT)
    def delete(
        self,
        parsed_path: Path[schemas.CommentIdPathSchema],
    ) -> None:
        """Soft-delete a comment, preserving the thread tree."""
        request: AuthenticatedCommentHttpRequest = self.request  # type: ignore[assignment]
        try:
            services.delete_comment(
                comment_id=parsed_path.comment_id,
                requester_profile_id=request.claims.profile_id,
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# COMMENT ARCHIVE: POST /api/v1/comments/{comment_id}/archive/
# ============================================================================


class CommentArchiveController(Controller[MsgspecSerializer]):
    """Archive or un-archive a comment thread.

    POST /api/v1/comments/{comment_id}/archive/
    """

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.OK)
    def post(
        self,
        parsed_path: Path[schemas.CommentIdPathSchema],
        parsed_body: Body[schemas.ArchiveCommentSchema],
    ) -> schemas.CommentResponseSchema:
        """Archive/unarchive a comment thread."""
        request: AuthenticatedCommentHttpRequest = self.request  # type: ignore[assignment]
        try:
            doc = services.archive_comment(
                comment_id=parsed_path.comment_id,
                requester_profile_id=request.claims.profile_id,
                is_archived=parsed_body.is_archived,
            )
            return serialize_comment(doc)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


# ============================================================================
# COMMENT VOTE: POST /api/v1/comments/{comment_id}/vote/
# ============================================================================


class CommentVoteController(Controller[MsgspecSerializer]):
    """Cast, flip, or remove a vote on a comment.

    POST /api/v1/comments/{comment_id}/vote/
    """

    @modify(auth=(RS256JWTSyncAuth(),), status_code=HTTPStatus.OK)
    def post(
        self,
        parsed_path: Path[schemas.CommentIdPathSchema],
        parsed_body: Body[schemas.CommentVoteSchema],
    ) -> schemas.CommentVoteResponseSchema:
        """Vote on a comment (1, -1, 0)."""
        request: AuthenticatedCommentHttpRequest = self.request  # type: ignore[assignment]
        try:
            doc = services.vote_on_comment(
                comment_id=parsed_path.comment_id,
                voter_profile_id=request.claims.profile_id,
                value=parsed_body.value,
            )
            return schemas.CommentVoteResponseSchema(
                comment_id=doc["id"],
                upvotes_count=doc["upvotes_count"],
                downvotes_count=doc["downvotes_count"],
                popularity_score=doc["popularity_score"],
                user_vote=doc.get("user_vote"),
            )
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

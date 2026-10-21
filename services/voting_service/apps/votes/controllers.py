"""DMR Skinny Controllers for Voting Service.

Handles HTTP requests, component validation, rate limiting, and RS256 JWT auth.
All business rules and persistence are strictly delegated to services.py.
"""

from __future__ import annotations

from http import HTTPStatus
from uuid import UUID

from dmr import Controller, modify
from dmr.components import Body, Path
from dmr.plugins.msgspec import MsgspecSerializer
from dmr.throttling import Rate, SyncThrottle

from services.voting_service.apps.votes.schemas import (
    CommentVotePathSchema,
    PostVotePathSchema,
    UserVoteResponseSchema,
    VoteInputSchema,
    VoteResponseSchema,
)
from services.voting_service.apps.votes.services import (
    cast_or_toggle_vote,
    get_user_vote_status,
)
from services.voting_service.security import (
    AuthenticatedVotingHttpRequest,
    RS256JWTSyncAuth,
)
from shared.exceptions.base import (
    AuthenticationFailedException,
    DomainException,
    ValidationException,
)
from shared.exceptions.handlers import domain_exception_to_dmr_error


def _ensure_uuid(val: str | UUID, name: str) -> UUID:
    """Helper to safely ensure value is a UUID or raise domain ValidationException."""
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValidationException(f"Invalid UUID for {name}: '{val}'.") from exc


class PostVoteController(Controller[MsgspecSerializer]):
    """Cast, flip, or revoke vote on a Post."""

    @modify(
        status_code=HTTPStatus.OK,
        auth=(RS256JWTSyncAuth(),),
        throttling=[
            # Burst limit: 20/min
            SyncThrottle(20, Rate.minute),
            # Sustained limit: 200/hr
            SyncThrottle(200, Rate.hour),
        ],
    )
    def post(
        self,
        parsed_path: Path[PostVotePathSchema],
        parsed_body: Body[VoteInputSchema],
    ) -> VoteResponseSchema:
        """Cast, flip, or revoke vote on the target post."""
        request: AuthenticatedVotingHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        post_uuid = _ensure_uuid(parsed_path.post_id, "post_id")
        user_uuid = _ensure_uuid(request.claims.profile_id, "profile_id")

        try:
            result = cast_or_toggle_vote(
                user_profile_id=user_uuid,
                target_type="POST",
                target_id=post_uuid,
                value=parsed_body.value,
            )
            return VoteResponseSchema(data=result)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class PostUserVoteController(Controller[MsgspecSerializer]):
    """Fetch current user's active vote on a Post."""

    @modify(
        status_code=HTTPStatus.OK,
        auth=(RS256JWTSyncAuth(),),
    )
    def get(
        self,
        parsed_path: Path[PostVotePathSchema],
    ) -> UserVoteResponseSchema:
        """Return current voter's active vote status (+1, -1, or null)."""
        request: AuthenticatedVotingHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        post_uuid = _ensure_uuid(parsed_path.post_id, "post_id")
        user_uuid = _ensure_uuid(request.claims.profile_id, "profile_id")

        try:
            status_result = get_user_vote_status(
                user_profile_id=user_uuid,
                target_type="POST",
                target_id=post_uuid,
            )
            return UserVoteResponseSchema(data=status_result)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class CommentVoteController(Controller[MsgspecSerializer]):
    """Cast, flip, or revoke vote on a Comment."""

    @modify(
        status_code=HTTPStatus.OK,
        auth=(RS256JWTSyncAuth(),),
        throttling=[
            # Burst limit: 20/min
            SyncThrottle(20, Rate.minute),
            # Sustained limit: 200/hr
            SyncThrottle(200, Rate.hour),
        ],
    )
    def post(
        self,
        parsed_path: Path[CommentVotePathSchema],
        parsed_body: Body[VoteInputSchema],
    ) -> VoteResponseSchema:
        """Cast, flip, or revoke vote on the target comment."""
        request: AuthenticatedVotingHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        comment_uuid = _ensure_uuid(parsed_path.comment_id, "comment_id")
        user_uuid = _ensure_uuid(request.claims.profile_id, "profile_id")

        try:
            result = cast_or_toggle_vote(
                user_profile_id=user_uuid,
                target_type="COMMENT",
                target_id=comment_uuid,
                value=parsed_body.value,
            )
            return VoteResponseSchema(data=result)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc


class CommentUserVoteController(Controller[MsgspecSerializer]):
    """Fetch current user's active vote on a Comment."""

    @modify(
        status_code=HTTPStatus.OK,
        auth=(RS256JWTSyncAuth(),),
    )
    def get(
        self,
        parsed_path: Path[CommentVotePathSchema],
    ) -> UserVoteResponseSchema:
        """Return current voter's active vote status (+1, -1, or null)."""
        request: AuthenticatedVotingHttpRequest = self.request  # type: ignore[assignment]
        if not getattr(request, "claims", None):
            raise domain_exception_to_dmr_error(
                AuthenticationFailedException("Authentication credentials were not provided.")
            )

        comment_uuid = _ensure_uuid(parsed_path.comment_id, "comment_id")
        user_uuid = _ensure_uuid(request.claims.profile_id, "profile_id")

        try:
            status_result = get_user_vote_status(
                user_profile_id=user_uuid,
                target_type="COMMENT",
                target_id=comment_uuid,
            )
            return UserVoteResponseSchema(data=status_result)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

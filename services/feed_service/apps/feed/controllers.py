"""DMR Skinny Controllers for Feed & Ranking Service.

Exposes REST endpoints conforming to docs/architecture/02.api defenitions/07.feed/12.feed.md.
Follows DMR standards:
- Component parameter naming (parsed_query)
- Returns typed Msgspec DTOs
- RS256 Asymmetric JWT Auth
"""

from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus

from django.conf import settings
from django.db import connections
from dmr import Controller, modify
from dmr.components import Query
from dmr.plugins.msgspec import MsgspecSerializer

from services.feed_service.apps.feed.schemas import (
    ExploreFeedQuerySchema,
    FeedResponseSchema,
    FollowingFeedQuerySchema,
    ForumsFeedQuerySchema,
    HealthResponseSchema,
)
from services.feed_service.apps.feed.services import (
    get_explore_feed,
    get_following_feed,
    get_joined_forums_feed,
    get_redis_client,
)
from services.feed_service.security import RS256JWTSyncAuth
from shared.jwt.tokens import load_public_key, verify_and_decode_token


class ExploreFeedController(Controller[MsgspecSerializer]):
    """Global Discovery / Popular Feed endpoint.

    Serves 24-hour sliding window rankings from Redis Sorted Sets with sub-10ms response times.
    Public endpoint with optional Bearer token inspection for personalized vote context.
    """

    @modify(
        status_code=HTTPStatus.OK,
        tags=["Feeds"],
    )
    def get(self, parsed_query: Query[ExploreFeedQuerySchema]) -> FeedResponseSchema:
        user_profile_id = None
        auth_header = self.request.headers.get("Authorization") or self.request.META.get(
            "HTTP_AUTHORIZATION"
        )

        if auth_header:
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                try:
                    public_key = load_public_key(settings.JWT_PUBLIC_KEY_PATH)
                    claims = verify_and_decode_token(
                        token=parts[1],
                        public_key_pem=public_key,
                        expected_token_type="access",
                    )
                    user_profile_id = str(claims.profile_id or claims.user_id)
                except Exception:
                    pass

        return get_explore_feed(
            query=parsed_query,
            current_user_profile_id=user_profile_id,
        )


class ForumsFeedController(Controller[MsgspecSerializer]):
    """User Joined-Forums Feed endpoint.

    Aggregates posts strictly from forums the authenticated user has joined with APPROVED status.
    Requires RS256 JWT Authentication.
    """

    @modify(
        status_code=HTTPStatus.OK,
        auth=(RS256JWTSyncAuth(),),
        tags=["Feeds"],
    )
    def get(self, parsed_query: Query[ForumsFeedQuerySchema]) -> FeedResponseSchema:
        claims = self.request.claims
        user_profile_id = str(claims.profile_id or claims.user_id)

        return get_joined_forums_feed(
            query=parsed_query,
            user_profile_id=user_profile_id,
        )


class FollowingFeedController(Controller[MsgspecSerializer]):
    """Personalized Following Feed endpoint.

    Aggregates profile-level posts from creators the authenticated user follows.
    Requires RS256 JWT Authentication.
    """

    @modify(
        status_code=HTTPStatus.OK,
        auth=(RS256JWTSyncAuth(),),
        tags=["Feeds"],
    )
    def get(self, parsed_query: Query[FollowingFeedQuerySchema]) -> FeedResponseSchema:
        claims = self.request.claims
        user_profile_id = str(claims.profile_id or claims.user_id)

        return get_following_feed(
            query=parsed_query,
            user_profile_id=user_profile_id,
        )


class FeedHealthController(Controller[MsgspecSerializer]):
    """Service health and connectivity probe."""

    @modify(
        status_code=HTTPStatus.OK,
        tags=["System"],
    )
    def get(self) -> HealthResponseSchema:
        now_str = datetime.now(tz=UTC).isoformat()

        # Check Redis
        redis_status = "ok"
        try:
            r = get_redis_client()
            if not r.ping():
                redis_status = "unresponsive"
        except Exception as exc:
            redis_status = f"error: {exc}"

        # Check Voting DB
        voting_db_status = "ok"
        try:
            conn = connections.get("voting_db") or connections.get("default")
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            else:
                voting_db_status = "not_configured"
        except Exception as exc:
            voting_db_status = f"error: {exc}"

        # Check Mongo
        mongo_status = "ok"
        try:
            from services.feed_service.apps.feed.services import get_mongo_posts_collection

            col = get_mongo_posts_collection()
            col.find_one({}, {"_id": 1})
        except Exception as exc:
            mongo_status = f"error: {exc}"

        overall = (
            "healthy"
            if redis_status == "ok" and "error" not in voting_db_status and mongo_status == "ok"
            else "degraded"
        )

        return HealthResponseSchema(
            status=overall,
            service="feed_service",
            redis=redis_status,
            voting_db=voting_db_status,
            mongo=mongo_status,
            timestamp=now_str,
        )

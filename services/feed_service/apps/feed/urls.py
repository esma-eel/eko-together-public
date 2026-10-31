"""DMR Router for Feed and Ranking Service."""

from __future__ import annotations

from dmr.routing import Router, path

from services.feed_service.apps.feed.controllers import (
    ExploreFeedController,
    FeedHealthController,
    FollowingFeedController,
    ForumsFeedController,
)

api_router = Router(
    "api/",
    [
        path("v1/feeds/explore/", ExploreFeedController.as_view(), name="explore_feed"),
        path("v1/feeds/forums/", ForumsFeedController.as_view(), name="forums_feed"),
        path("v1/feeds/following/", FollowingFeedController.as_view(), name="following_feed"),
        path("v1/feeds/health/", FeedHealthController.as_view(), name="feed_health"),
    ],
)

"""Unified URLConf for test suite covering all monorepo microservices."""

from __future__ import annotations

from services.auth_user_service.apps.accounts.urls import (
    api_router as auth_api_router,
)
from services.auth_user_service.apps.accounts.urls import (
    internal_router as auth_internal_router,
)
from services.forum_service.apps.forums.urls import (
    api_router as forum_api_router,
)
from services.forum_service.apps.forums.urls import (
    internal_router as forum_internal_router,
)
from services.media_service.apps.media.urls import (
    api_router as media_api_router,
)
from services.post_comment_service.apps.comments.urls import (
    api_router as comments_api_router,
)
from services.post_comment_service.apps.posts.urls import (
    api_router as posts_api_router,
)
from services.voting_service.apps.votes.urls import (
    api_router as votes_api_router,
)
from services.feed_service.apps.feed.urls import (
    api_router as feed_api_router,
)
from services.search_service.apps.search.urls import (
    api_router as search_api_router,
)

urlpatterns = [
    # Auth Service endpoints
    auth_api_router.to_urlpatterns(),
    auth_internal_router.to_urlpatterns(),
    # Forum Service endpoints
    forum_api_router.to_urlpatterns(),
    forum_internal_router.to_urlpatterns(),
    # Media Service endpoints
    media_api_router.to_urlpatterns(),
    # Post & Comment Service endpoints
    posts_api_router.to_urlpatterns(),
    comments_api_router.to_urlpatterns(),
    # Voting Service endpoints
    votes_api_router.to_urlpatterns(),
    # Feed Service endpoints
    feed_api_router.to_urlpatterns(),
    # Search Service endpoints
    search_api_router.to_urlpatterns(),
]

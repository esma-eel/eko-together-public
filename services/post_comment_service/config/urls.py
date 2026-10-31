"""Root URL configuration for Post & Comment Service."""

from __future__ import annotations

from dmr.openapi import build_schema
from dmr.openapi.views import OpenAPIJsonView, SwaggerView
from dmr.plugins.msgspec import MsgspecSerializer
from dmr.routing import Router, build_404_handler, build_500_handler, path

from services.post_comment_service.apps.comments.urls import (
    api_router as comments_api_router,
)
from services.post_comment_service.apps.posts.urls import (
    api_router as posts_api_router,
)

api_router = Router(
    "api/",
    [
        *posts_api_router.urls,
        *comments_api_router.urls,
    ],
)

openapi_schema = build_schema(api_router)

urlpatterns = [
    # All combined public API endpoints
    api_router.to_urlpatterns(),
    # Interactive API Documentation
    path("docs/openapi.json", OpenAPIJsonView.as_view(openapi_schema), name="openapi_json"),
    path("docs/swagger/", SwaggerView.as_view(openapi_schema), name="swagger_ui"),
]

# JSON-formatted 404 & 500 error handlers
handler404 = build_404_handler("api/", serializer=MsgspecSerializer)
handler500 = build_500_handler("api/", serializer=MsgspecSerializer)

from __future__ import annotations

from dmr.openapi import build_schema
from dmr.openapi.views import OpenAPIJsonView, SwaggerView
from dmr.plugins.msgspec import MsgspecSerializer
from dmr.routing import build_404_handler, build_500_handler, path

from services.search_service.apps.search.urls import api_router

openapi_schema = build_schema(api_router)

urlpatterns = [
    api_router.to_urlpatterns(),
    path("docs/openapi.json", OpenAPIJsonView.as_view(openapi_schema), name="openapi_json"),
    path("docs/swagger/", SwaggerView.as_view(openapi_schema), name="swagger_ui"),
]

handler404 = build_404_handler("api/", serializer=MsgspecSerializer)
handler500 = build_500_handler("api/", serializer=MsgspecSerializer)


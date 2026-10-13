"""Routing definitions for Media Service endpoints.

Uses dmr.routing.Router and dmr.routing.path for high-performance prefix-matched dispatch.
"""

from __future__ import annotations

from dmr.routing import Router, path

from services.media_service.apps.media.controllers import (
    MediaUploadUrlController,
)

api_router = Router(
    "api/",
    [
        path("v1/media/upload-url/", MediaUploadUrlController.as_view(), name="media_upload_url"),
    ],
)

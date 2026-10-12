"""Typed DTO Schemas for Media Service.

Built using high-performance msgspec.Struct for instantaneous validation and serialization.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

import msgspec


class MediaPurpose(StrEnum):
    """Allowed upload intent purposes for storage partitioning."""

    POST_ATTACHMENT = "POST_ATTACHMENT"
    FORUM_AVATAR = "FORUM_AVATAR"
    FORUM_COVER = "FORUM_COVER"
    USER_AVATAR = "USER_AVATAR"


ALLOWED_CONTENT_TYPES: Final[set[str]] = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}

MAX_FILE_SIZE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB (10485760 bytes)
DEFAULT_URL_EXPIRY_SECONDS: Final[int] = 300  # 5 minutes


class PresignedUploadRequestSchema(msgspec.Struct, kw_only=True):
    """Payload for requesting an S3/MinIO presigned upload URL."""

    filename: str
    content_type: str
    file_size_bytes: int
    purpose: str = MediaPurpose.POST_ATTACHMENT.value


class PresignedUploadResponseSchema(msgspec.Struct, kw_only=True):
    """Response containing signed direct upload URL and permanent CDN locator."""

    upload_url: str
    cdn_url: str
    file_key: str
    expires_in_seconds: int = DEFAULT_URL_EXPIRY_SECONDS
    http_method: str = "PUT"
    required_headers: dict[str, str]

"""Domain services for Media and Asset Upload orchestration."""

from __future__ import annotations

import datetime
import os
import uuid
from typing import Final
from uuid import UUID

from services.media_service.apps.media.schemas import (
    ALLOWED_CONTENT_TYPES,
    DEFAULT_URL_EXPIRY_SECONDS,
    MAX_FILE_SIZE_BYTES,
    MediaPurpose,
    PresignedUploadRequestSchema,
    PresignedUploadResponseSchema,
)
from services.media_service.apps.media.storage import S3MediaStorage
from shared.exceptions.base import DomainException

MIME_EXTENSION_MAP: Final[dict[str, str]] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

PURPOSE_FOLDER_MAP: Final[dict[str, str]] = {
    MediaPurpose.POST_ATTACHMENT.value: "uploads/posts",
    MediaPurpose.FORUM_AVATAR.value: "uploads/forums/avatars",
    MediaPurpose.FORUM_COVER.value: "uploads/forums/covers",
    MediaPurpose.USER_AVATAR.value: "uploads/users/avatars",
}


class InvalidMediaPayloadException(DomainException):
    """Raised when incoming media upload parameters violate business rules (HTTP 400)."""

    default_message = "Invalid media upload parameters."
    default_code = "INVALID_MEDIA_PAYLOAD"
    status_code = 400


def validate_upload_request(payload: PresignedUploadRequestSchema) -> None:
    """Validate incoming upload parameters against course and API specifications."""
    # 1. Filename validation
    if not payload.filename or not payload.filename.strip():
        raise InvalidMediaPayloadException(
            message="Filename cannot be empty.",
            code="INVALID_FILENAME",
        )

    # 2. MIME type whitelist validation
    clean_content_type = payload.content_type.strip().lower()
    if clean_content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidMediaPayloadException(
            message=(
                f"Unsupported MIME type '{payload.content_type}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}."
            ),
            code="INVALID_MIME_TYPE",
            details={"allowed_types": sorted(ALLOWED_CONTENT_TYPES)},
        )

    # 3. File size validation (1 byte <= size <= 10MB)
    if payload.file_size_bytes <= 0:
        raise InvalidMediaPayloadException(
            message="File size must be greater than 0 bytes.",
            code="FILE_SIZE_ZERO",
        )

    if payload.file_size_bytes > MAX_FILE_SIZE_BYTES:
        raise InvalidMediaPayloadException(
            message=(
                f"File size ({payload.file_size_bytes} bytes) exceeds maximum "
                f"allowed threshold of {MAX_FILE_SIZE_BYTES} bytes (10MB)."
            ),
            code="FILE_TOO_LARGE",
            details={
                "max_size_bytes": MAX_FILE_SIZE_BYTES,
                "provided_size_bytes": payload.file_size_bytes,
            },
        )

    # 4. Purpose validation
    valid_purposes = {p.value for p in MediaPurpose}
    if payload.purpose not in valid_purposes:
        raise InvalidMediaPayloadException(
            message=(
                f"Invalid upload purpose '{payload.purpose}'. "
                f"Allowed purposes: {', '.join(sorted(valid_purposes))}."
            ),
            code="INVALID_PURPOSE",
            details={"allowed_purposes": sorted(valid_purposes)},
        )


def generate_file_key(
    *,
    filename: str,
    content_type: str,
    purpose: str,
    asset_id: UUID | None = None,
    now: datetime.datetime | None = None,
) -> str:
    """Construct hierarchical, collision-free S3 file key.

    Format:
        uploads/{category}/{year}/{month:02d}/{uuid}{extension}

    Examples:
        uploads/posts/2026/10/9b1deb4d-3b7d-4bad.png
        uploads/forums/avatars/2026/10/7c4f4b23-9a3d.jpg
    """
    current_time = now or datetime.datetime.now(datetime.UTC)
    year = current_time.year
    month = f"{current_time.month:02d}"
    unique_id = str(asset_id or uuid.uuid4())

    folder_prefix = PURPOSE_FOLDER_MAP.get(purpose, "uploads/general")

    # Determine extension
    ext = os.path.splitext(filename)[1].lower()
    if not ext or len(ext) > 5:
        ext = MIME_EXTENSION_MAP.get(content_type.lower(), ".bin")

    return f"{folder_prefix}/{year}/{month}/{unique_id}{ext}"


def create_presigned_upload(
    payload: PresignedUploadRequestSchema,
    *,
    storage: S3MediaStorage | None = None,
) -> PresignedUploadResponseSchema:
    """Execute end-to-end presigned upload URL issuance workflow.

    Args:
        payload: Validated upload request DTO.
        storage: Optional injected S3 storage engine (defaults to configured instance).

    Returns:
        PresignedUploadResponseSchema with upload_url, cdn_url, file_key, and required headers.
    """
    validate_upload_request(payload)

    storage_client = storage or S3MediaStorage()
    content_type = payload.content_type.strip().lower()

    file_key = generate_file_key(
        filename=payload.filename,
        content_type=content_type,
        purpose=payload.purpose,
    )

    upload_url = storage_client.generate_presigned_put_url(
        file_key=file_key,
        content_type=content_type,
        expires_in=DEFAULT_URL_EXPIRY_SECONDS,
    )

    cdn_url = storage_client.build_cdn_url(file_key)

    return PresignedUploadResponseSchema(
        upload_url=upload_url,
        cdn_url=cdn_url,
        file_key=file_key,
        expires_in_seconds=DEFAULT_URL_EXPIRY_SECONDS,
        http_method="PUT",
        required_headers={"Content-Type": content_type},
    )

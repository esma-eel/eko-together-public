"""Controllers for Media presigned URL generation and direct uploads."""

from __future__ import annotations

from http import HTTPStatus

from dmr import Body, Controller, modify
from dmr.plugins.msgspec import MsgspecSerializer
from dmr.throttling import Rate, SyncThrottle

from services.media_service.apps.media.schemas import (
    PresignedUploadRequestSchema,
    PresignedUploadResponseSchema,
)
from services.media_service.apps.media.security import (
    RS256JWTSyncAuth,
    UserClaimsProfileThrottleKey,
)
from services.media_service.apps.media.services import create_presigned_upload
from shared.exceptions.base import DomainException
from shared.exceptions.handlers import domain_exception_to_dmr_error


class MediaUploadUrlController(Controller[MsgspecSerializer]):
    """Issue short-lived presigned upload URLs for direct binary uploads to MinIO/S3."""

    @modify(
        auth=(RS256JWTSyncAuth(),),
        throttling=(
            SyncThrottle(
                30,
                Rate.minute,
                cache_key=UserClaimsProfileThrottleKey(),
            ),
        ),
        status_code=HTTPStatus.OK,
    )
    def post(
        self,
        parsed_body: Body[PresignedUploadRequestSchema],
    ) -> PresignedUploadResponseSchema:
        """Generate a 5-minute presigned PUT URL for direct client-to-storage upload.

        Validates MIME types (JPEG, PNG, WebP, GIF) and maximum file size (10 MB).
        Clients use the returned URL to PUT the binary payload directly into MinIO/S3,
        bypassing the application backend.
        """
        try:
            return create_presigned_upload(parsed_body)
        except DomainException as exc:
            raise domain_exception_to_dmr_error(exc) from exc

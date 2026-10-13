"""Tests for Media Presigned URL Generation and Direct S3/MinIO Upload."""

from http import HTTPStatus
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest
from dmr.test import DMRClient

from services.media_service.apps.media.schemas import (
    MAX_FILE_SIZE_BYTES,
    MediaPurpose,
    PresignedUploadRequestSchema,
)
from services.media_service.apps.media.services import (
    create_presigned_upload,
    generate_file_key,
)
from services.media_service.apps.media.storage import S3MediaStorage


def test_generate_presigned_url_post_attachment_success(
    client: DMRClient,
    auth_headers: dict[str, str],
    valid_upload_payload: dict[str, object],
) -> None:
    """Validate 200 OK and presigned upload response structure for post attachment."""
    response = client.post("/api/v1/media/upload-url/", data=valid_upload_payload, **auth_headers)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert "upload_url" in data
    assert "cdn_url" in data
    assert "file_key" in data
    assert data["expires_in_seconds"] == 300
    assert data["http_method"] == "PUT"
    assert data["required_headers"] == {"Content-Type": "image/png"}

    # Verify hierarchical path structure
    file_key = data["file_key"]
    assert file_key.startswith("uploads/posts/")
    assert file_key.endswith(".png")

    # Verify CDN URL mirrors file key
    assert data["cdn_url"].endswith(file_key)

    # Verify presigned URL points to storage endpoint and has PUT parameters
    parsed_upload_url = urlparse(data["upload_url"])
    assert "forum-media" in parsed_upload_url.path or "uploads/posts" in parsed_upload_url.path
    has_amz_param = (
        "X-Amz-Signature" in parsed_upload_url.query or "X-Amz-Algorithm" in parsed_upload_url.query
    )
    assert has_amz_param


@pytest.mark.parametrize(
    ("purpose", "expected_prefix"),
    [
        (MediaPurpose.POST_ATTACHMENT.value, "uploads/posts/"),
        (MediaPurpose.FORUM_AVATAR.value, "uploads/forums/avatars/"),
        (MediaPurpose.FORUM_COVER.value, "uploads/forums/covers/"),
        (MediaPurpose.USER_AVATAR.value, "uploads/users/avatars/"),
    ],
)
def test_generate_presigned_url_for_all_purposes(
    client: DMRClient,
    auth_headers: dict[str, str],
    purpose: str,
    expected_prefix: str,
) -> None:
    """Validate distinct storage folders partitioned per upload purpose."""
    payload = {
        "filename": "asset.jpg",
        "content_type": "image/jpeg",
        "file_size_bytes": 500000,
        "purpose": purpose,
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.OK
    data = response.json()

    assert data["file_key"].startswith(expected_prefix)
    assert data["file_key"].endswith(".jpg")
    assert data["required_headers"] == {"Content-Type": "image/jpeg"}


@pytest.mark.parametrize(
    ("content_type", "expected_ext"),
    [
        ("image/jpeg", ".jpg"),
        ("image/png", ".png"),
        ("image/webp", ".webp"),
        ("image/gif", ".gif"),
    ],
)
def test_generate_presigned_url_for_all_allowed_mimes(
    client: DMRClient,
    auth_headers: dict[str, str],
    content_type: str,
    expected_ext: str,
) -> None:
    """Validate all whitelisted MIME types are accepted with matching extensions."""
    payload = {
        "filename": f"sample{expected_ext}",
        "content_type": content_type,
        "file_size_bytes": 1024,
        "purpose": MediaPurpose.POST_ATTACHMENT.value,
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["file_key"].endswith(expected_ext)
    assert data["required_headers"] == {"Content-Type": content_type}


@pytest.mark.parametrize(
    "invalid_mime",
    [
        "text/plain",
        "application/pdf",
        "video/mp4",
        "image/svg+xml",
        "application/octet-stream",
        "application/javascript",
    ],
)
def test_reject_unsupported_mime_types(
    client: DMRClient,
    auth_headers: dict[str, str],
    invalid_mime: str,
) -> None:
    """Validate 400 Bad Request when requesting upload for non-whitelisted MIME type."""
    payload = {
        "filename": "payload.bin",
        "content_type": invalid_mime,
        "file_size_bytes": 2048,
        "purpose": MediaPurpose.POST_ATTACHMENT.value,
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data["code"] == "INVALID_MIME_TYPE"


def test_reject_file_size_exceeding_10mb(
    client: DMRClient,
    auth_headers: dict[str, str],
) -> None:
    """Validate 400 Bad Request when file size exceeds 10 MB (10485760 bytes)."""
    payload = {
        "filename": "huge-image.png",
        "content_type": "image/png",
        "file_size_bytes": MAX_FILE_SIZE_BYTES + 1,  # 10 MB + 1 byte
        "purpose": MediaPurpose.POST_ATTACHMENT.value,
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data["code"] == "FILE_TOO_LARGE"


@pytest.mark.parametrize("invalid_size", [0, -1, -5000])
def test_reject_zero_or_negative_file_size(
    client: DMRClient,
    auth_headers: dict[str, str],
    invalid_size: int,
) -> None:
    """Validate 400 Bad Request when file size is zero or negative."""
    payload = {
        "filename": "empty.png",
        "content_type": "image/png",
        "file_size_bytes": invalid_size,
        "purpose": MediaPurpose.POST_ATTACHMENT.value,
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data["code"] == "FILE_SIZE_ZERO"


@pytest.mark.parametrize("empty_filename", ["", "   "])
def test_reject_empty_filename(
    client: DMRClient,
    auth_headers: dict[str, str],
    empty_filename: str,
) -> None:
    """Validate 400 Bad Request when filename is empty or blank."""
    payload = {
        "filename": empty_filename,
        "content_type": "image/png",
        "file_size_bytes": 1024,
        "purpose": MediaPurpose.POST_ATTACHMENT.value,
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data["code"] == "INVALID_FILENAME"


def test_reject_invalid_purpose(
    client: DMRClient,
    auth_headers: dict[str, str],
) -> None:
    """Validate 400 Bad Request when upload purpose is unrecognized."""
    payload = {
        "filename": "avatar.png",
        "content_type": "image/png",
        "file_size_bytes": 1024,
        "purpose": "UNAUTHORIZED_FOLDER_PURPOSE",
    }
    response = client.post("/api/v1/media/upload-url/", data=payload, **auth_headers)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    data = response.json()
    assert data["code"] == "INVALID_PURPOSE"


def test_unauthenticated_request_rejected(
    client: DMRClient,
    valid_upload_payload: dict[str, object],
) -> None:
    """Validate 401 Unauthorized when Authorization header is omitted."""
    response = client.post("/api/v1/media/upload-url/", data=valid_upload_payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_invalid_bearer_token_rejected(
    client: DMRClient,
    valid_upload_payload: dict[str, object],
) -> None:
    """Validate 401 Unauthorized when Bearer token is tampered or invalid."""
    bad_headers = {"HTTP_AUTHORIZATION": "Bearer invalid.jwt.token.here"}
    response = client.post("/api/v1/media/upload-url/", data=valid_upload_payload, **bad_headers)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_storage_unit_generation_and_cdn_builder() -> None:
    """Unit test storage abstraction with custom/mocked client."""
    mock_boto = MagicMock()
    mock_boto.generate_presigned_url.return_value = (
        "https://s3.example.com/bucket/uploads/posts/mock.png?signature=123"
    )

    storage = S3MediaStorage(
        client=mock_boto,
        bucket_name="custom-bucket",
        cdn_base_url="https://cdn.example.com",
    )

    presigned_url = storage.generate_presigned_put_url(
        file_key="uploads/posts/mock.png",
        content_type="image/png",
        expires_in=300,
    )
    assert presigned_url.startswith("https://s3.example.com")
    mock_boto.generate_presigned_url.assert_called_once_with(
        ClientMethod="put_object",
        Params={
            "Bucket": "custom-bucket",
            "Key": "uploads/posts/mock.png",
            "ContentType": "image/png",
        },
        ExpiresIn=300,
        HttpMethod="PUT",
    )

    cdn_url = storage.build_cdn_url("uploads/posts/mock.png")
    assert cdn_url == "https://cdn.example.com/uploads/posts/mock.png"


def test_domain_create_presigned_upload_direct() -> None:
    """Validate domain service create_presigned_upload with injected mock storage."""
    mock_storage = MagicMock(spec=S3MediaStorage)
    mock_storage.generate_presigned_put_url.return_value = "https://mock-s3.com/upload"
    mock_storage.build_cdn_url.return_value = "https://cdn.example.com/mock.png"

    payload = PresignedUploadRequestSchema(
        filename="diagram.png",
        content_type="image/png",
        file_size_bytes=4096,
        purpose=MediaPurpose.POST_ATTACHMENT.value,
    )

    result = create_presigned_upload(payload, storage=mock_storage)
    assert result.upload_url == "https://mock-s3.com/upload"
    assert result.cdn_url == "https://cdn.example.com/mock.png"
    assert result.expires_in_seconds == 300
    assert result.http_method == "PUT"
    assert result.required_headers == {"Content-Type": "image/png"}


def test_generate_file_key_uniqueness() -> None:
    """Validate that consecutive calls generate unique file keys even for identical parameters."""
    key1 = generate_file_key(
        filename="photo.jpg",
        content_type="image/jpeg",
        purpose=MediaPurpose.USER_AVATAR.value,
    )
    key2 = generate_file_key(
        filename="photo.jpg",
        content_type="image/jpeg",
        purpose=MediaPurpose.USER_AVATAR.value,
    )
    assert key1 != key2
    assert key1.startswith("uploads/users/avatars/")
    assert key2.startswith("uploads/users/avatars/")

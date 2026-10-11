"""Object Storage abstraction for S3 and MinIO presigned uploads."""

from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)


class S3MediaStorage:
    """Manages S3 and MinIO direct-to-object-store operations."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        bucket_name: str | None = None,
        cdn_base_url: str | None = None,
        endpoint_url: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        use_ssl: bool | None = None,
    ) -> None:
        self.bucket_name = bucket_name or getattr(settings, "MINIO_BUCKET_NAME", "forum-media")
        self.cdn_base_url = (
            cdn_base_url
            or getattr(settings, "CDN_BASE_URL", None)
            or getattr(settings, "MINIO_PUBLIC_URL", "http://localhost:9000/forum-media")
        )

        if client is not None:
            self._client = client
        else:
            endpoint = endpoint_url or getattr(settings, "MINIO_ENDPOINT", "localhost:9000")
            is_ssl = (
                use_ssl
                if use_ssl is not None
                else getattr(settings, "MINIO_USE_SSL", False)
            )
            scheme = "https" if is_ssl else "http"
            full_endpoint = endpoint if "://" in endpoint else f"{scheme}://{endpoint}"

            self._client = boto3.client(
                "s3",
                endpoint_url=full_endpoint,
                aws_access_key_id=aws_access_key_id
                or getattr(settings, "MINIO_ROOT_USER", "minio_admin"),
                aws_secret_access_key=aws_secret_access_key
                or getattr(settings, "MINIO_ROOT_PASSWORD", "minio_password"),
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                region_name=region_name or getattr(settings, "S3_REGION_NAME", "us-east-1"),
            )

    @property
    def client(self) -> Any:
        """Underlying Boto3 client instance."""
        return self._client

    def generate_presigned_put_url(
        self,
        *,
        file_key: str,
        content_type: str,
        expires_in: int = 300,
    ) -> str:
        """Generate a short-lived presigned URL for direct binary PUT upload.

        Args:
            file_key: Unique target key/path inside the bucket.
            content_type: Expected MIME type for Content-Type matching.
            expires_in: Time to live in seconds (default 300s / 5 minutes).

        Returns:
            Fully qualified presigned PUT URL.
        """
        presigned_url: str = self._client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": file_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )
        return presigned_url

    def build_cdn_url(self, file_key: str) -> str:
        """Construct public CDN or Object Store read URL for the stored key.

        Args:
            file_key: Stored asset path.

        Returns:
            Direct public CDN or MinIO URL.
        """
        base = self.cdn_base_url.rstrip("/")
        clean_key = file_key.lstrip("/")
        return f"{base}/{clean_key}"

    def ensure_bucket_exists(self) -> bool:
        """Ensure the target bucket exists and has public read access.

        Returns:
            True if bucket exists or was created, False on connection failure.
        """
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                try:
                    self._client.create_bucket(Bucket=self.bucket_name)
                    # Configure public read policy for CDN / MinIO simulation
                    public_policy = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Sid": "PublicReadGetObject",
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["s3:GetObject"],
                                "Resource": [f"arn:aws:s3:::{self.bucket_name}/*"],
                            }
                        ],
                    }
                    self._client.put_bucket_policy(
                        Bucket=self.bucket_name,
                        Policy=json.dumps(public_policy),
                    )
                    return True
                except Exception as create_exc:
                    logger.warning("Could not create bucket %s: %s", self.bucket_name, create_exc)
                    return False
            logger.warning("Could not inspect bucket %s: %s", self.bucket_name, exc)
            return False
        except Exception as exc:
            logger.warning("MinIO / S3 offline or unreachable: %s", exc)
            return False

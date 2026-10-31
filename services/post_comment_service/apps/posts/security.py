"""Decentralized RS256 JWT Authentication for Posts application.

Re-exports centralized Post & Comment Service security components for backwards
compatibility and clean decoupled imports.
"""

from __future__ import annotations

from services.post_comment_service.security import (
    AuthenticatedPostCommentHttpRequest,
    AuthenticatedPostHttpRequest,
    OptionalRS256JWTSyncAuth,
    RS256JWTSyncAuth,
)

__all__ = [
    "AuthenticatedPostCommentHttpRequest",
    "AuthenticatedPostHttpRequest",
    "OptionalRS256JWTSyncAuth",
    "RS256JWTSyncAuth",
]

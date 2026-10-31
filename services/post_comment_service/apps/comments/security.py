"""Decentralized RS256 JWT Authentication for Comments application.

Re-exports centralized Post & Comment Service security components for clean decoupled imports.
"""

from __future__ import annotations

from services.post_comment_service.security import (
    AuthenticatedCommentHttpRequest,
    AuthenticatedPostCommentHttpRequest,
    OptionalRS256JWTSyncAuth,
    RS256JWTSyncAuth,
)

__all__ = [
    "AuthenticatedCommentHttpRequest",
    "AuthenticatedPostCommentHttpRequest",
    "OptionalRS256JWTSyncAuth",
    "RS256JWTSyncAuth",
]

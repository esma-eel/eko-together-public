"""User and authentication domain events."""

from __future__ import annotations

from uuid import UUID

from shared.events.base import BaseEvent


class UserRegisteredEvent(BaseEvent, kw_only=True):
    """Emitted when a new user registers in Auth Service."""

    event_type: str = "user.registered"
    user_id: UUID
    profile_id: UUID
    username: str
    email: str


class UserProfileUpdatedEvent(BaseEvent, kw_only=True):
    """Emitted when user profile metadata changes, for Search and Caches."""

    event_type: str = "profile.updated"
    user_id: UUID
    profile_id: UUID
    display_name: str
    username: str = ""
    bio: str = ""
    avatar: str | None = None
    is_private: bool = False

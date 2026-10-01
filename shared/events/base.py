"""Base event definitions and serialization using msgspec."""

from __future__ import annotations

import datetime
from typing import TypeVar
from uuid import UUID, uuid4

import msgspec

T = TypeVar("T", bound="BaseEvent")


class BaseEvent(msgspec.Struct, kw_only=True):
    """Abstract base event contract for message bus payloads."""

    event_id: UUID = msgspec.field(default_factory=uuid4)
    event_type: str
    occurred_at: str = msgspec.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat()
    )
    version: str = "1.0"


def serialize_event(event: BaseEvent) -> bytes:
    """Serialize an event instance into JSON bytes."""
    return msgspec.json.encode(event)


def deserialize_event[T: BaseEvent](payload: bytes | str, event_cls: type[T]) -> T:
    """Deserialize JSON payload into the specified typed event class."""
    return msgspec.json.decode(payload, type=event_cls)

"""Voting domain events published by Voting Service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from shared.events.base import BaseEvent


class VoteCastEvent(BaseEvent, kw_only=True):
    """Emitted immediately after a vote is created or flipped in Voting DB."""

    event_type: str = "vote.cast"
    target_type: Literal["POST", "COMMENT"]
    target_id: UUID
    user_profile_id: UUID
    delta_up: int  # 1 or 0
    delta_down: int  # 1 or 0
    net_delta: int  # -2, -1, +1, +2


class VoteRevokedEvent(BaseEvent, kw_only=True):
    """Emitted when a user cancels/retracts their vote."""

    event_type: str = "vote.revoked"
    target_type: Literal["POST", "COMMENT"]
    target_id: UUID
    user_profile_id: UUID
    previous_value: int  # +1 or -1

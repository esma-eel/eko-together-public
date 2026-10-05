"""Internal Inter-Service DMR Controllers.

Allows downstream services (e.g., Post & Comment Service) to verify relationship
boundaries without direct physical database joins.
"""

from __future__ import annotations

import uuid

from dmr import Controller, Query
from dmr.plugins.msgspec import MsgspecSerializer

from services.auth_user_service.apps.accounts.models import (
    RelationStatusChoices,
    UserRelation,
)
from services.auth_user_service.apps.accounts.schemas import (
    InternalRelationCheckQueryDTO,
    InternalRelationCheckResponseDTO,
)
from shared.exceptions.base import ValidationException
from shared.exceptions.handlers import domain_exception_to_dmr_error


class InternalRelationCheckController(Controller[MsgspecSerializer]):
    """Internal lightweight endpoint for other services to verify social graph relations."""

    def get(
        self,
        parsed_query: Query[InternalRelationCheckQueryDTO],
    ) -> InternalRelationCheckResponseDTO:
        """Check whether follower_id has an accepted or pending relationship to target_id."""
        try:
            follower_uuid = uuid.UUID(parsed_query.follower_id)
            target_uuid = uuid.UUID(parsed_query.target_id)
        except ValueError as exc:
            raise domain_exception_to_dmr_error(
                ValidationException("Invalid follower_id or target_id UUID format.")
            ) from exc

        relation = UserRelation.objects.filter(
            follower_profile_id=follower_uuid,
            following_profile_id=target_uuid,
        ).first()

        if not relation:
            return InternalRelationCheckResponseDTO(is_following=False, status="NONE")

        is_accepted = relation.status == RelationStatusChoices.ACCEPTED
        return InternalRelationCheckResponseDTO(
            is_following=is_accepted,
            status=relation.status,
        )

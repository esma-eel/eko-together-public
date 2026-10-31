"""Domain logic and business services for Forum Microservice.

Handles transactional operations for sub-communities, member lifecycle,
role elevation, post pinning quota guards, and inter-service permission checking.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils.text import slugify

from services.forum_service.apps.forums.models import (
    Forum,
    ForumMember,
    ForumPinnedPost,
    MemberRoleChoices,
    MemberStatusChoices,
    PostPermissionChoices,
)
from shared.events.forums import (
    ForumCreatedEvent,
    ForumDeletedEvent,
    ForumMemberJoinedEvent,
    ForumMemberLeftEvent,
    ForumUpdatedEvent,
)
from shared.exceptions.base import (
    ConflictException,
    EntityNotFoundException,
    PermissionDeniedException,
    ValidationException,
)

if TYPE_CHECKING:
    from services.forum_service.apps.forums.schemas import (
        ForumCreateSchema,
        ForumUpdateSchema,
    )


def validate_slug(slug: str) -> str:
    """Validate slug format (lowercase alphanumeric and hyphens)."""
    cleaned = slug.strip().lower()
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", cleaned):
        raise ValidationException(
            "Slug must contain only lowercase alphanumeric characters and single hyphens."
        )
    return cleaned


@transaction.atomic
def create_forum(
    owner_profile_id: UUID,
    payload: ForumCreateSchema,
) -> Forum:
    """Create a new sub-community forum and register owner membership."""
    slug = validate_slug(payload.slug or slugify(payload.title))

    if Forum.objects.filter(slug=slug).exists():
        raise ConflictException(f"A forum with slug '{slug}' already exists.")

    valid_permissions = [c.value for c in PostPermissionChoices]
    if payload.post_permission not in valid_permissions:
        msg = (
            f"Invalid post_permission: '{payload.post_permission}'. "
            f"Must be one of {valid_permissions}."
        )
        raise ValidationException(msg)

    forum = Forum.objects.create(
        owner_profile_id=owner_profile_id,
        title=payload.title.strip(),
        slug=slug,
        description=payload.description.strip(),
        rules=payload.rules.strip(),
        avatar=payload.avatar,
        cover_image=payload.cover_image,
        post_permission=payload.post_permission,
        require_approval_to_join=payload.require_approval_to_join,
        is_comments_locked=payload.is_comments_locked,
        members_count=1,
    )

    # Automatically enroll creator as OWNER with APPROVED status
    ForumMember.objects.create(
        forum=forum,
        user_profile_id=owner_profile_id,
        role=MemberRoleChoices.OWNER,
        status=MemberStatusChoices.APPROVED,
    )

    # Construct event for downstream search & feed indexing
    _ = ForumCreatedEvent(
        forum_id=forum.id,
        title=forum.title,
        slug=forum.slug,
        owner_profile_id=forum.owner_profile_id,
    )

    return forum


def get_forum_by_slug(slug: str) -> Forum:
    """Fetch forum by slug or raise EntityNotFoundException."""
    forum = Forum.objects.filter(slug=slug).first()
    if not forum:
        raise EntityNotFoundException(f"Forum with slug '{slug}' does not exist.")
    return forum


def get_forum_by_id(forum_id: UUID | str) -> Forum:
    """Fetch forum by UUID or raise EntityNotFoundException."""
    forum = Forum.objects.filter(id=forum_id).first()
    if not forum:
        raise EntityNotFoundException(f"Forum with id '{forum_id}' does not exist.")
    return forum


@transaction.atomic
def update_forum(
    forum: Forum,
    operator_profile_id: UUID,
    payload: ForumUpdateSchema,
) -> Forum:
    """Update forum settings and metadata. Restricted to Owner or Admin."""
    member = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=operator_profile_id,
        status=MemberStatusChoices.APPROVED,
    ).first()

    if not member or member.role not in (MemberRoleChoices.OWNER, MemberRoleChoices.ADMIN):
        raise PermissionDeniedException("Only forum owners and admins can update forum settings.")

    if payload.title is not None:
        forum.title = payload.title.strip()
    if payload.description is not None:
        forum.description = payload.description.strip()
    if payload.rules is not None:
        forum.rules = payload.rules.strip()
    if payload.avatar is not None:
        forum.avatar = payload.avatar
    if payload.cover_image is not None:
        forum.cover_image = payload.cover_image
    if payload.require_approval_to_join is not None:
        forum.require_approval_to_join = payload.require_approval_to_join
    if payload.post_permission is not None:
        valid_permissions = [c.value for c in PostPermissionChoices]
        if payload.post_permission not in valid_permissions:
            msg = (
                f"Invalid post_permission: '{payload.post_permission}'. "
                f"Must be one of {valid_permissions}."
            )
            raise ValidationException(msg)
        forum.post_permission = payload.post_permission
    if payload.is_comments_locked is not None:
        forum.is_comments_locked = payload.is_comments_locked

    forum.save()

    _ = ForumUpdatedEvent(
        forum_id=forum.id,
        title=forum.title,
        slug=forum.slug,
        is_comments_locked=forum.is_comments_locked,
    )

    return forum


@transaction.atomic
def delete_forum(forum: Forum, operator_profile_id: UUID) -> None:
    """Delete a forum. Restricted strictly to the forum Owner."""
    if forum.owner_profile_id != operator_profile_id:
        raise PermissionDeniedException("Only the forum owner can delete this forum.")

    forum_id = forum.id
    slug = forum.slug
    forum.delete()

    _ = ForumDeletedEvent(
        forum_id=forum_id,
        slug=slug,
    )


@transaction.atomic
def join_or_apply_forum(
    forum: Forum,
    user_profile_id: UUID,
) -> tuple[str, str]:
    """Join or apply to join a forum.

    Returns:
        tuple of (status: 'PENDING' | 'APPROVED', message: str)
    """
    existing = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=user_profile_id,
    ).first()

    if existing:
        if existing.status == MemberStatusChoices.BANNED:
            raise PermissionDeniedException("You are banned from participating in this forum.")
        if existing.status == MemberStatusChoices.APPROVED:
            raise ConflictException("You are already an approved member of this forum.")
        if existing.status == MemberStatusChoices.PENDING:
            msg = "Your membership application is currently pending admin review."
            raise ConflictException(msg)

    if forum.require_approval_to_join:
        ForumMember.objects.create(
            forum=forum,
            user_profile_id=user_profile_id,
            role=MemberRoleChoices.MEMBER,
            status=MemberStatusChoices.PENDING,
        )
        return (MemberStatusChoices.PENDING.value, "Join request submitted for admin review.")

    ForumMember.objects.create(
        forum=forum,
        user_profile_id=user_profile_id,
        role=MemberRoleChoices.MEMBER,
        status=MemberStatusChoices.APPROVED,
    )
    Forum.objects.filter(id=forum.id).update(members_count=F("members_count") + 1)
    forum.refresh_from_db(fields=["members_count"])

    _ = ForumMemberJoinedEvent(
        forum_id=forum.id,
        user_profile_id=user_profile_id,
        role=MemberRoleChoices.MEMBER.value,
    )
    return (MemberStatusChoices.APPROVED.value, "Joined forum successfully.")


@transaction.atomic
def leave_forum(
    forum: Forum,
    user_profile_id: UUID,
) -> None:
    """Leave a forum. Owners cannot leave without deleting or transferring ownership."""
    member = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=user_profile_id,
    ).first()

    if not member:
        raise EntityNotFoundException("You are not a member of this forum.")

    if member.role == MemberRoleChoices.OWNER:
        msg = (
            "The forum owner cannot leave the forum. "
            "Transfer ownership or delete the forum instead."
        )
        raise ValidationException(msg)

    if member.status == MemberStatusChoices.APPROVED:
        Forum.objects.filter(id=forum.id, members_count__gt=0).update(
            members_count=F("members_count") - 1
        )
        forum.refresh_from_db(fields=["members_count"])

    member.delete()

    _ = ForumMemberLeftEvent(
        forum_id=forum.id,
        user_profile_id=user_profile_id,
    )


@transaction.atomic
def update_member_role_or_status(
    forum: Forum,
    operator_profile_id: UUID,
    target_profile_id: UUID,
    role: str | None = None,
    status: str | None = None,
) -> ForumMember:
    """Moderate a forum member (promote, demote, approve, ban).

    Rules:
        - Admin can approve/ban standard MEMBERs.
        - Only Owner can promote/demote ADMIN.
        - Neither Admin nor Owner can ban or demote Owner.
    """
    operator = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=operator_profile_id,
        status=MemberStatusChoices.APPROVED,
    ).first()

    if not operator or operator.role not in (MemberRoleChoices.OWNER, MemberRoleChoices.ADMIN):
        raise PermissionDeniedException("Only forum owners and admins can moderate members.")

    target = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=target_profile_id,
    ).first()

    if not target:
        raise EntityNotFoundException("Target member was not found in this forum.")

    # Rule: Cannot modify or ban the owner
    if target.role == MemberRoleChoices.OWNER:
        raise PermissionDeniedException("Cannot modify role or status of the forum owner.")

    # Rule: Admin restrictions
    if operator.role == MemberRoleChoices.ADMIN:
        if target.role == MemberRoleChoices.ADMIN:
            raise PermissionDeniedException("Admins cannot modify fellow admins.")
        if role in (MemberRoleChoices.ADMIN.value, MemberRoleChoices.OWNER.value):
            msg = "Only the forum owner can promote users to Admin or Owner."
            raise PermissionDeniedException(msg)

    # Status transition tracking for members_count
    old_status = target.status
    new_status = status or old_status

    if role is not None:
        valid_roles = [r.value for r in MemberRoleChoices]
        if role not in valid_roles:
            raise ValidationException(f"Invalid role: '{role}'. Must be one of {valid_roles}.")
        target.role = role

    if status is not None:
        valid_statuses = [s.value for s in MemberStatusChoices]
        if status not in valid_statuses:
            msg = f"Invalid status: '{status}'. Must be one of {valid_statuses}."
            raise ValidationException(msg)
        target.status = status

    target.save()

    # Update members_count if status changed
    if old_status != MemberStatusChoices.APPROVED and new_status == MemberStatusChoices.APPROVED:
        Forum.objects.filter(id=forum.id).update(members_count=F("members_count") + 1)
        forum.refresh_from_db(fields=["members_count"])
    elif old_status == MemberStatusChoices.APPROVED and new_status in (
        MemberStatusChoices.BANNED,
        MemberStatusChoices.PENDING,
    ):
        Forum.objects.filter(id=forum.id, members_count__gt=0).update(
            members_count=F("members_count") - 1
        )
        forum.refresh_from_db(fields=["members_count"])

    return target


@transaction.atomic
def kick_member(
    forum: Forum,
    operator_profile_id: UUID,
    target_profile_id: UUID,
) -> None:
    """Kick or remove a user from the forum."""
    operator = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=operator_profile_id,
        status=MemberStatusChoices.APPROVED,
    ).first()

    if not operator or operator.role not in (MemberRoleChoices.OWNER, MemberRoleChoices.ADMIN):
        raise PermissionDeniedException("Only forum owners and admins can remove members.")

    target = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=target_profile_id,
    ).first()

    if not target:
        raise EntityNotFoundException("Target member was not found in this forum.")

    if target.role == MemberRoleChoices.OWNER:
        raise PermissionDeniedException("Cannot remove the forum owner.")

    if operator.role == MemberRoleChoices.ADMIN and target.role == MemberRoleChoices.ADMIN:
        raise PermissionDeniedException("Admins cannot remove fellow admins.")

    if target.status == MemberStatusChoices.APPROVED:
        Forum.objects.filter(id=forum.id, members_count__gt=0).update(
            members_count=F("members_count") - 1
        )
        forum.refresh_from_db(fields=["members_count"])

    target.delete()


@transaction.atomic
def pin_or_unpin_post(
    forum: Forum,
    operator_profile_id: UUID,
    post_id: UUID,
    is_pinned: bool,
    pin_order: int = 1,
) -> tuple[UUID, bool, int, int]:
    """Pin or unpin a post in the forum, guarding the 10-pinned-posts quota.

    Returns:
        tuple of (post_id, is_pinned, pin_order, active_pins_count)
    """
    operator = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=operator_profile_id,
        status=MemberStatusChoices.APPROVED,
    ).first()

    if not operator or operator.role not in (MemberRoleChoices.OWNER, MemberRoleChoices.ADMIN):
        raise PermissionDeniedException("Only forum owners and admins can pin or unpin posts.")

    if not (0 <= pin_order <= 10):
        raise ValidationException("Pin order must be between 0 and 10.")

    if is_pinned:
        active_count = (
            ForumPinnedPost.objects.filter(forum=forum, is_pinned=True)
            .exclude(post_id=post_id)
            .count()
        )
        if active_count >= 10:
            raise ValidationException("Maximum 10 pinned posts allowed per forum.")

        ForumPinnedPost.objects.update_or_create(
            forum=forum,
            post_id=post_id,
            defaults={
                "is_pinned": True,
                "pin_order": pin_order,
                "pinned_by_profile_id": operator_profile_id,
            },
        )
        total_active = active_count + 1
        return (post_id, True, pin_order, total_active)

    ForumPinnedPost.objects.filter(forum=forum, post_id=post_id).update(is_pinned=False)
    total_active = ForumPinnedPost.objects.filter(forum=forum, is_pinned=True).count()
    return (post_id, False, pin_order, total_active)


def check_post_permission(
    forum: Forum,
    user_profile_id: UUID,
    admin_visibility: str = "ALL",
) -> tuple[bool, str | None, str | None, str | None]:
    """Verify if a user profile is authorized to post in the forum.

    Returns:
        tuple of (can_post, user_role, user_status, reason)
    """
    member = ForumMember.objects.filter(
        forum=forum,
        user_profile_id=user_profile_id,
    ).first()

    role = member.role if member else None
    status = member.status if member else None

    # Check read-only state
    if forum.post_permission == PostPermissionChoices.NO_ONE:
        return (False, role, status, "Forum is currently read-only.")

    # Check ban
    if member and member.status == MemberStatusChoices.BANNED:
        return (False, role, status, "User is banned from this forum.")

    # Check admin visibility post submission
    if admin_visibility == "ADMINS_ONLY":
        if not (member and member.role in (MemberRoleChoices.OWNER, MemberRoleChoices.ADMIN)):
            msg = "Only admins and the owner can publish admin-visibility posts."
            return (False, role, status, msg)

    # Evaluate forum post_permission policy
    if forum.post_permission == PostPermissionChoices.ADMINS_ONLY:
        is_admin_or_owner = (
            member is not None
            and member.role in (MemberRoleChoices.OWNER, MemberRoleChoices.ADMIN)
            and member.status == MemberStatusChoices.APPROVED
        )
        if is_admin_or_owner:
            return (True, role, status, None)
        return (False, role, status, "Only admins and the owner can post in this forum.")

    if forum.post_permission == PostPermissionChoices.APPROVED_ONLY:
        if member and member.status == MemberStatusChoices.APPROVED:
            return (True, role, status, None)
        return (False, role, status, "Membership approval is required to post in this forum.")

    if forum.post_permission == PostPermissionChoices.ALL_MEMBERS:
        if member and member.status != MemberStatusChoices.BANNED:
            return (True, role, status, None)
        return (False, role, status, "User must belong to the forum and not be banned to post.")

    return (False, role, status, "Unauthorized to post in this forum.")

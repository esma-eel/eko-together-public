"""Database models for Forum Microservice.

Polyglot PostgreSQL database mapping for forums, sub-community memberships,
and forum-wide post pinning rules.
"""

from __future__ import annotations

import uuid

from django.db import models


class PostPermissionChoices(models.TextChoices):
    """Permissions regulating who can submit posts into a forum."""

    ALL_MEMBERS = "ALL_MEMBERS", "All Members"
    APPROVED_ONLY = "APPROVED_ONLY", "Approved Members Only"
    ADMINS_ONLY = "ADMINS_ONLY", "Admins Only"
    NO_ONE = "NO_ONE", "No One (Read-Only)"


class MemberRoleChoices(models.TextChoices):
    """Role hierarchy within a forum sub-community."""

    OWNER = "OWNER", "Owner"
    ADMIN = "ADMIN", "Admin"
    MEMBER = "MEMBER", "Member"


class MemberStatusChoices(models.TextChoices):
    """Membership state within a forum."""

    PENDING = "PENDING", "Pending Approval"
    APPROVED = "APPROVED", "Approved"
    BANNED = "BANNED", "Banned"


class Forum(models.Model):
    """Sub-community forum entity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_profile_id = models.UUIDField(
        db_index=True,
        help_text="Logical UUID reference to UserProfile.id",
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    rules = models.TextField(blank=True, default="")
    avatar = models.URLField(max_length=500, blank=True, null=True)
    cover_image = models.URLField(max_length=500, blank=True, null=True)

    post_permission = models.CharField(
        max_length=20,
        choices=PostPermissionChoices.choices,
        default=PostPermissionChoices.ALL_MEMBERS,
        db_index=True,
    )
    require_approval_to_join = models.BooleanField(default=False)
    is_comments_locked = models.BooleanField(default=False)
    members_count = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "forums"
        ordering = ["-created_at"]
        verbose_name = "Forum"
        verbose_name_plural = "Forums"

    def __str__(self) -> str:
        return f"{self.title} ({self.slug})"


class ForumMember(models.Model):
    """Membership edge connecting a user profile to a forum."""

    id = models.BigAutoField(primary_key=True)
    forum = models.ForeignKey(
        Forum,
        on_delete=models.CASCADE,
        related_name="members",
        db_index=True,
    )
    user_profile_id = models.UUIDField(
        db_index=True,
        help_text="Logical UUID reference to UserProfile.id",
    )
    role = models.CharField(
        max_length=20,
        choices=MemberRoleChoices.choices,
        default=MemberRoleChoices.MEMBER,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=MemberStatusChoices.choices,
        default=MemberStatusChoices.APPROVED,
        db_index=True,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "forum_members"
        constraints = [
            models.UniqueConstraint(
                fields=["forum", "user_profile_id"],
                name="unique_forum_member",
            ),
        ]
        indexes = [
            models.Index(fields=["forum", "role"]),
            models.Index(fields=["forum", "status"]),
        ]
        verbose_name = "Forum Member"
        verbose_name_plural = "Forum Members"

    def __str__(self) -> str:
        return f"Profile {self.user_profile_id} in {self.forum.slug} ({self.role}:{self.status})"


class ForumPinnedPost(models.Model):
    """Pinned post record for a forum, enforcing max 10 pinned posts."""

    id = models.BigAutoField(primary_key=True)
    forum = models.ForeignKey(
        Forum,
        on_delete=models.CASCADE,
        related_name="pinned_posts",
        db_index=True,
    )
    post_id = models.UUIDField(db_index=True, help_text="Logical UUID reference to PostDocument.id")
    pin_order = models.PositiveSmallIntegerField(default=1)
    is_pinned = models.BooleanField(default=True, db_index=True)
    pinned_by_profile_id = models.UUIDField(help_text="Logical UUID reference to UserProfile.id")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "forum_pinned_posts"
        constraints = [
            models.UniqueConstraint(
                fields=["forum", "post_id"],
                name="unique_forum_pinned_post",
            ),
        ]
        indexes = [
            models.Index(fields=["forum", "is_pinned", "pin_order"]),
        ]
        ordering = ["pin_order", "-created_at"]
        verbose_name = "Forum Pinned Post"
        verbose_name_plural = "Forum Pinned Posts"

    def __str__(self) -> str:
        return f"Post {self.post_id} pinned in {self.forum.slug} (order {self.pin_order})"

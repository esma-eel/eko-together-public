"""Database models for User & Auth Service.

Implements User (credentials/auth), UserProfile (domain persona),
UserRelation (follower/following social graph with privacy approval),
UserActionLog (audit stream), and RevokedToken (logout blacklist).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class UserManager(BaseUserManager):
    """Custom user manager for UUID-based User model."""

    def create_user(
        self,
        username: str,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        """Create and persist a regular user with profile."""
        if not username:
            raise ValueError("The Username field must be set.")
        if not email:
            raise ValueError("The Email field must be set.")

        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        username: str,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> User:
        """Create and persist a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Minimal identity and credentials model with UUID primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        return self.username


class PostVisibilityChoices(models.TextChoices):
    PUBLIC = "PUBLIC", "Public"
    FOLLOWERS_ONLY = "FOLLOWERS_ONLY", "Followers Only"
    PRIVATE = "PRIVATE", "Private"


class CommentPermissionChoices(models.TextChoices):
    ANYONE = "ANYONE", "Anyone"
    FOLLOWERS_ONLY = "FOLLOWERS_ONLY", "Followers Only"
    NO_ONE = "NO_ONE", "No One"


class UserProfile(models.Model):
    """Domain persona and profile settings for a User."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=100)
    avatar = models.CharField(max_length=500, blank=True, default="")
    bio = models.TextField(blank=True, default="")
    is_private = models.BooleanField(default=False)

    # User default privacy preferences
    default_post_visibility = models.CharField(
        max_length=20,
        choices=PostVisibilityChoices.choices,
        default=PostVisibilityChoices.PUBLIC,
    )
    default_comment_permission = models.CharField(
        max_length=20,
        choices=CommentPermissionChoices.choices,
        default=CommentPermissionChoices.ANYONE,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self) -> str:
        return f"{self.display_name} (@{self.user.username})"

    # Persistent Counter Cache fields (eliminated on-the-fly COUNT(*) overhead)
    followers_count = models.PositiveIntegerField(default=0, db_index=True)
    following_count = models.PositiveIntegerField(default=0, db_index=True)


class RelationStatusChoices(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"


class UserRelation(models.Model):
    """Directed social graph edge between two profiles (following/follower)."""

    id = models.BigAutoField(primary_key=True)
    follower_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="following_relations",
    )
    following_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="follower_relations",
    )
    status = models.CharField(
        max_length=20,
        choices=RelationStatusChoices.choices,
        default=RelationStatusChoices.ACCEPTED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_relations"
        verbose_name = "User Relation"
        verbose_name_plural = "User Relations"
        constraints = [
            models.UniqueConstraint(
                fields=["follower_profile", "following_profile"],
                name="unique_follower_following",
            ),
            models.CheckConstraint(
                condition=~models.Q(follower_profile=models.F("following_profile")),
                name="prevent_self_follow",
            ),
        ]
        indexes = [
            models.Index(
                fields=["following_profile", "status", "-created_at"],
                name="idx_rel_following_status_dt",
            ),
            models.Index(
                fields=["follower_profile", "status", "-created_at"],
                name="idx_rel_follower_status_dt",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"@{self.follower_profile.user.username} -> "
            f"@{self.following_profile.user.username} ({self.status})"
        )


class UserActionLog(models.Model):
    """Audit and security activity log for operations performed across services."""

    id = models.BigAutoField(primary_key=True)
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_logs",
    )
    target_type = models.CharField(max_length=32, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    action = models.CharField(max_length=64, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "user_action_logs"
        verbose_name = "User Action Log"
        verbose_name_plural = "User Action Logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        actor = self.user_profile.user.username if self.user_profile else "Anonymous"
        return f"[{self.created_at}] {actor}: {self.action}"


class RevokedToken(models.Model):
    """Token blacklist repository for logout and immediate revocation."""

    id = models.BigAutoField(primary_key=True)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    token_type = models.CharField(max_length=20, default="refresh")
    user_id = models.UUIDField(null=True, blank=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "revoked_tokens"
        verbose_name = "Revoked Token"
        verbose_name_plural = "Revoked Tokens"

    def __str__(self) -> str:
        return f"RevokedToken({self.token_hash[:10]}...)"

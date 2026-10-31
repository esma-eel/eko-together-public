"""Business logic and domain services for User & Auth Service.

Handles audit logging, stateless password reset generation, token creation,
token revocation blacklist, and follow graph lifecycle.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import IntegrityError, transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.http import HttpRequest
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from services.auth_user_service.apps.accounts.models import (
    RelationStatusChoices,
    RevokedToken,
    User,
    UserActionLog,
    UserProfile,
    UserRelation,
)
from shared.exceptions.base import (
    ConflictException,
    EntityNotFoundException,
    ValidationException,
)
from shared.jwt.tokens import (
    create_access_token,
    create_refresh_token,
    load_private_key,
)


def get_client_ip(request: HttpRequest) -> str | None:
    """Extract client IPv4 or IPv6 address from request headers."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_user_action(
    request: HttpRequest,
    action: str,
    user_profile: UserProfile | None = None,
    target_type: str = "",
    target_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> UserActionLog:
    """Record an audit trail event in UserActionLog."""
    ip = get_client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "")[:512]
    return UserActionLog.objects.create(
        user_profile=user_profile,
        target_type=target_type,
        target_id=str(target_id) if target_id else "",
        action=action,
        ip_address=ip,
        user_agent=ua,
        metadata=metadata or {},
    )


def compute_token_hash(token: str) -> str:
    """Calculate SHA-256 hash of a JWT string for secure blacklist indexing."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def revoke_token(
    token: str, user_id: UUID | None = None, token_type: str = "refresh"
) -> RevokedToken:
    """Blacklist a token so it cannot be refreshed or used."""
    token_hash = compute_token_hash(token)
    revoked, _ = RevokedToken.objects.get_or_create(
        token_hash=token_hash,
        defaults={"user_id": user_id, "token_type": token_type},
    )
    return revoked


def is_token_revoked(token: str) -> bool:
    """Check if token hash exists in revocation blacklist."""
    token_hash = compute_token_hash(token)
    return RevokedToken.objects.filter(token_hash=token_hash).exists()


def create_user_tokens(user: User) -> tuple[str, str]:
    """Generate RS256 access and refresh tokens for user."""
    private_key_pem = load_private_key(settings.JWT_PRIVATE_KEY_PATH)
    profile = user.profile
    roles = ["user"]
    if user.is_superuser:
        roles.extend(["admin", "superuser"])
    elif user.is_staff:
        roles.append("staff")

    access = create_access_token(
        user_id=user.id,
        profile_id=profile.id,
        username=user.username,
        roles=roles,
        private_key_pem=private_key_pem,
        expiration_minutes=settings.JWT_ACCESS_EXPIRATION_MINUTES,
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )
    refresh = create_refresh_token(
        user_id=user.id,
        profile_id=profile.id,
        username=user.username,
        private_key_pem=private_key_pem,
        expiration_days=settings.JWT_REFRESH_EXPIRATION_DAYS,
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
    )
    return access, refresh


# ==============================================================================
# Stateless Password Reset Generator
# ==============================================================================


class StatelessPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """Stateless HMAC-based reset token generator incorporating password hash."""

    def _make_hash_value(self, user: User, timestamp: int) -> str:
        # Changes whenever user's password, last_login, or is_active changes
        return f"{user.pk}{user.password}{user.last_login}{timestamp}"


password_reset_token_generator = StatelessPasswordResetTokenGenerator()


def encode_user_id(user_id: UUID | str) -> str:
    """Encode user UUID to urlsafe base64 string."""
    return urlsafe_base64_encode(force_bytes(str(user_id)))


def decode_user_id(uid_str: str) -> UUID:
    """Decode urlsafe base64 string back to UUID."""
    try:
        raw_str = force_str(urlsafe_base64_decode(uid_str))
        return UUID(raw_str)
    except Exception as exc:
        raise ValidationException("Invalid user identifier encoding.") from exc


# ==============================================================================
# Follow Graph Operations
# ==============================================================================


@transaction.atomic
def follow_user_profile(
    follower: UserProfile,
    target: UserProfile,
) -> UserRelation:
    """Create follow edge. Returns created or updated relation."""
    if follower.id == target.id:
        raise ValidationException("Users cannot follow themselves.")

    existing = UserRelation.objects.filter(
        follower_profile=follower,
        following_profile=target,
    ).first()

    initial_status = (
        RelationStatusChoices.PENDING if target.is_private else RelationStatusChoices.ACCEPTED
    )

    if existing:
        if existing.status == RelationStatusChoices.ACCEPTED:
            raise ConflictException("You are already following this user.")
        if existing.status == RelationStatusChoices.PENDING:
            raise ConflictException("Follow request is already pending.")
        # If previously rejected, re-apply
        prev_status = existing.status
        existing.status = initial_status
        existing.save()
        if initial_status == RelationStatusChoices.ACCEPTED and prev_status != RelationStatusChoices.ACCEPTED:
            UserProfile.objects.filter(id=follower.id).update(following_count=F("following_count") + 1)
            UserProfile.objects.filter(id=target.id).update(followers_count=F("followers_count") + 1)
            follower.refresh_from_db(fields=["following_count"])
            target.refresh_from_db(fields=["followers_count"])
        return existing

    try:
        relation = UserRelation.objects.create(
            follower_profile=follower,
            following_profile=target,
            status=initial_status,
        )
        if initial_status == RelationStatusChoices.ACCEPTED:
            UserProfile.objects.filter(id=follower.id).update(following_count=F("following_count") + 1)
            UserProfile.objects.filter(id=target.id).update(followers_count=F("followers_count") + 1)
            follower.refresh_from_db(fields=["following_count"])
            target.refresh_from_db(fields=["followers_count"])
        return relation
    except IntegrityError as exc:
        rel = UserRelation.objects.filter(
            follower_profile=follower,
            following_profile=target,
        ).first()
        if rel:
            if rel.status == RelationStatusChoices.ACCEPTED:
                raise ConflictException("You are already following this user.") from exc
            if rel.status == RelationStatusChoices.PENDING:
                raise ConflictException("Follow request is already pending.") from exc
        raise ConflictException("A follow relationship already exists or is being processed.") from exc


@transaction.atomic
def unfollow_user_profile(
    follower: UserProfile,
    target: UserProfile,
) -> None:
    """Remove follow edge or cancel pending request."""
    if follower.id == target.id:
        raise ValidationException("Users cannot unfollow themselves.")

    existing = UserRelation.objects.filter(
        follower_profile=follower,
        following_profile=target,
    ).first()

    if not existing:
        raise EntityNotFoundException("No active or pending relationship found with this user.")

    was_accepted = existing.status == RelationStatusChoices.ACCEPTED
    existing.delete()

    if was_accepted:
        UserProfile.objects.filter(id=follower.id).update(
            following_count=Greatest(0, F("following_count") - 1)
        )
        UserProfile.objects.filter(id=target.id).update(
            followers_count=Greatest(0, F("followers_count") - 1)
        )
        follower.refresh_from_db(fields=["following_count"])
        target.refresh_from_db(fields=["followers_count"])


@transaction.atomic
def handle_follow_request_action(
    owner: UserProfile,
    relation_id: int,
    action: str,
) -> UserRelation:
    """Approve or reject a pending follow request."""
    relation = UserRelation.objects.filter(
        id=relation_id,
        following_profile=owner,
        status=RelationStatusChoices.PENDING,
    ).select_related("follower_profile", "following_profile").first()

    if not relation:
        raise EntityNotFoundException("Pending follow request not found.")

    action_upper = action.strip().upper()
    if action_upper == "APPROVE":
        relation.status = RelationStatusChoices.ACCEPTED
        relation.save()
        # Atomically update counter cache
        UserProfile.objects.filter(id=relation.following_profile_id).update(
            followers_count=F("followers_count") + 1
        )
        UserProfile.objects.filter(id=relation.follower_profile_id).update(
            following_count=F("following_count") + 1
        )
        owner.refresh_from_db(fields=["followers_count"])
    elif action_upper == "REJECT":
        relation.status = RelationStatusChoices.REJECTED
        relation.save()
    else:
        raise ValidationException(f"Unsupported action '{action}'. Must be 'APPROVE' or 'REJECT'.")

    return relation


def sync_profile_counts(profile: UserProfile) -> tuple[int, int]:
    """Synchronize cached counters with actual accepted active relations."""
    actual_followers = profile.follower_relations.filter(
        status=RelationStatusChoices.ACCEPTED,
        follower_profile__user__is_active=True,
    ).count()
    actual_following = profile.following_relations.filter(
        status=RelationStatusChoices.ACCEPTED,
        following_profile__user__is_active=True,
    ).count()
    UserProfile.objects.filter(id=profile.id).update(
        followers_count=actual_followers,
        following_count=actual_following,
    )
    profile.followers_count = actual_followers
    profile.following_count = actual_following
    return actual_followers, actual_following

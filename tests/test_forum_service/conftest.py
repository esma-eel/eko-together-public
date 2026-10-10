"""Shared fixtures for Forum Service test suite."""

import uuid
from pathlib import Path
from uuid import UUID

import pytest
from django.conf import settings
from dmr.test import DMRClient, DMRRequestFactory

from services.forum_service.apps.forums.models import (
    Forum,
    ForumMember,
    MemberRoleChoices,
    MemberStatusChoices,
    PostPermissionChoices,
)
from shared.jwt.tokens import create_access_token, load_private_key


@pytest.fixture
def client() -> DMRClient:
    """Fixture providing DMR test client with JSON content negotiation."""
    return DMRClient()


@pytest.fixture
def rf() -> DMRRequestFactory:
    """Fixture providing DMR request factory."""
    return DMRRequestFactory()


@pytest.fixture
def private_key_pem() -> bytes:
    """Load RSA private key for minting signed test JWTs."""
    key_path = getattr(settings, "JWT_PRIVATE_KEY_PATH", None)
    if not key_path:
        root_dir = Path(__file__).resolve().parent.parent.parent
        key_path = root_dir / "shared" / "jwt" / "private_key.pem"
    return load_private_key(key_path)


@pytest.fixture
def owner_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def admin_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def member_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def stranger_profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def banned_profile_id() -> UUID:
    return uuid.uuid4()


def make_auth_headers(profile_id: UUID, username: str, private_key_pem: bytes) -> dict[str, str]:
    token = create_access_token(
        user_id=uuid.uuid4(),
        profile_id=profile_id,
        username=username,
        roles=["user"],
        private_key_pem=private_key_pem,
    )
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture
def owner_headers(owner_profile_id: UUID, private_key_pem: bytes) -> dict[str, str]:
    return make_auth_headers(owner_profile_id, "forum_owner", private_key_pem)


@pytest.fixture
def admin_headers(admin_profile_id: UUID, private_key_pem: bytes) -> dict[str, str]:
    return make_auth_headers(admin_profile_id, "forum_admin", private_key_pem)


@pytest.fixture
def member_headers(member_profile_id: UUID, private_key_pem: bytes) -> dict[str, str]:
    return make_auth_headers(member_profile_id, "forum_member", private_key_pem)


@pytest.fixture
def stranger_headers(stranger_profile_id: UUID, private_key_pem: bytes) -> dict[str, str]:
    return make_auth_headers(stranger_profile_id, "stranger_user", private_key_pem)


@pytest.fixture
def banned_headers(banned_profile_id: UUID, private_key_pem: bytes) -> dict[str, str]:
    return make_auth_headers(banned_profile_id, "banned_user", private_key_pem)


@pytest.fixture
def sample_forum(
    db,
    owner_profile_id: UUID,
    admin_profile_id: UUID,
    member_profile_id: UUID,
    banned_profile_id: UUID,
) -> Forum:
    """Pre-populated forum with owner, admin, approved member, and banned member."""
    forum = Forum.objects.create(
        owner_profile_id=owner_profile_id,
        title="Distributed Systems & Microservices",
        slug="distributed-systems",
        description="Deep dives into distributed architecture.",
        rules="1. Be kind.\n2. Provide reproducible benchmarks.",
        post_permission=PostPermissionChoices.ALL_MEMBERS,
        require_approval_to_join=False,
        is_comments_locked=False,
        members_count=3,
    )
    # Owner
    ForumMember.objects.create(
        forum=forum,
        user_profile_id=owner_profile_id,
        role=MemberRoleChoices.OWNER,
        status=MemberStatusChoices.APPROVED,
    )
    # Admin
    ForumMember.objects.create(
        forum=forum,
        user_profile_id=admin_profile_id,
        role=MemberRoleChoices.ADMIN,
        status=MemberStatusChoices.APPROVED,
    )
    # Member
    ForumMember.objects.create(
        forum=forum,
        user_profile_id=member_profile_id,
        role=MemberRoleChoices.MEMBER,
        status=MemberStatusChoices.APPROVED,
    )
    # Banned
    ForumMember.objects.create(
        forum=forum,
        user_profile_id=banned_profile_id,
        role=MemberRoleChoices.MEMBER,
        status=MemberStatusChoices.BANNED,
    )
    return forum

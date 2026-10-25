"""Shared fixtures and setup for Feed & Ranking Service test suite."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import mongomock
import pytest
from dmr.test import DMRClient

from shared.jwt.tokens import create_access_token, load_private_key


class MockRedis:
    """In-memory Redis mock supporting Sorted Sets and atomic key operations."""

    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}

    def pipeline(self) -> MockRedisPipeline:
        return MockRedisPipeline(self)

    def ping(self) -> bool:
        return True

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.zsets:
                del self.zsets[k]
                count += 1
        return count

    def rename(self, src: str, dst: str) -> bool:
        if src in self.zsets:
            self.zsets[dst] = dict(self.zsets[src])
            del self.zsets[src]
            return True
        return False

    def zadd(self, name: str, mapping: dict[str, float]) -> int:
        if name not in self.zsets:
            self.zsets[name] = {}
        for member, score in mapping.items():
            self.zsets[name][str(member)] = float(score)
        return len(mapping)

    def zrevrange(self, name: str, start: int, end: int, withscores: bool = False) -> list[Any]:
        zset = self.zsets.get(name, {})
        # Sort descending by score, tiebreak by member string descending
        sorted_items = sorted(zset.items(), key=lambda x: (x[1], x[0]), reverse=True)
        if end == -1:
            slice_items = sorted_items[start:]
        else:
            slice_items = sorted_items[start : end + 1]
        if withscores:
            return slice_items
        return [item[0] for item in slice_items]

    def zrevrangebyscore(
        self,
        name: str,
        max: float | str,
        min: float | str = "-inf",
        start: int | None = None,
        num: int | None = None,
        withscores: bool = False,
    ) -> list[Any]:
        zset = self.zsets.get(name, {})
        max_val = float("inf") if max in ("+inf", "+INF") else float(max)
        min_val = float("-inf") if min in ("-inf", "-INF") else float(min)

        filtered = [
            (member, score) for member, score in zset.items() if min_val <= score <= max_val
        ]
        sorted_items = sorted(filtered, key=lambda x: (x[1], x[0]), reverse=True)

        if start is not None and num is not None:
            sorted_items = sorted_items[start : start + num]

        if withscores:
            return sorted_items
        return [item[0] for item in sorted_items]


class MockRedisPipeline:
    def __init__(self, redis_instance: MockRedis) -> None:
        self.redis = redis_instance
        self.commands: list[tuple[str, tuple, dict]] = []

    def delete(self, *keys: str):
        self.commands.append(("delete", keys, {}))
        return self

    def zadd(self, name: str, mapping: dict[str, float]):
        self.commands.append(("zadd", (name, mapping), {}))
        return self

    def rename(self, src: str, dst: str):
        self.commands.append(("rename", (src, dst), {}))
        return self

    def execute(self) -> list[Any]:
        results = []
        for cmd, args, kwargs in self.commands:
            method = getattr(self.redis, cmd)
            results.append(method(*args, **kwargs))
        self.commands.clear()
        return results


@pytest.fixture
def mock_redis() -> MockRedis:
    return MockRedis()


@pytest.fixture
def mock_mongo():
    """In-memory mongomock posts collection."""
    client = mongomock.MongoClient()
    db = client["test_feed_mongo"]
    col = db["posts"]
    return col


@pytest.fixture
def client() -> DMRClient:
    return DMRClient()


@pytest.fixture
def private_key_pem() -> bytes:
    root_dir = Path(__file__).resolve().parent.parent.parent
    key_path = root_dir / "keys" / "private_key.pem"
    if not key_path.exists():
        key_path = root_dir / "shared" / "jwt" / "private_key.pem"
    return load_private_key(key_path)


@pytest.fixture
def user_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def profile_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def auth_headers(private_key_pem: bytes, user_id: UUID, profile_id: UUID) -> dict[str, str]:
    token = create_access_token(
        user_id=user_id,
        profile_id=profile_id,
        username="feeduser",
        roles=["user"],
        private_key_pem=private_key_pem,
        expiration_minutes=60,
    )
    return {
        "HTTP_AUTHORIZATION": f"Bearer {token}",
        "Authorization": f"Bearer {token}",
    }

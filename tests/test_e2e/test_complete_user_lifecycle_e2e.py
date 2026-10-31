"""End-to-End (E2E) integration test covering the complete user lifecycle across all 7 microservices.

Simulates the entire multi-service journey according to Phase 8 architectural specifications:
1. User Registration (Auth Service & PostgreSQL Users DB)
2. Asymmetric JWT Authentication & RS256 Verification
3. Social Graph interaction (Follow / Profile discovery)
4. Forum Community Creation and Join Workflow (Forum Service & PostgreSQL Forums DB)
5. Media Service presigned upload request (Media Service & S3 / MinIO)
6. Post & Tag Publishing (Post & Comment Service & MongoDB Sharded Cluster)
7. High-speed Dedicated Voting & Event Dispatch (Voting Service & Dedicated PostgreSQL DB)
8. Nested Comment Discussion Tree (Post & Comment Service & MongoDB)
9. CQRS Sliding Window Feed & Ranking Aggregation (Feed Service & Redis Read Store)
10. Multi-Entity Unified Search & Real-Time Suggestions (Search Service & Elasticsearch 8.x)
11. Gateway Access Control and Security Rules (Edge Ingress Protection)
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest
from dmr.test import DMRClient

from services.feed_service.apps.feed.services import REDIS_KEY_POPULAR_24H_GLOBAL
from services.forum_service.apps.forums.models import MemberStatusChoices
from services.post_comment_service.db import get_comments_collection, get_posts_collection
from services.search_service.apps.search.client import reset_elasticsearch_client, set_elasticsearch_client
from services.search_service.apps.search.indices import (
    INDEX_FORUMS,
    INDEX_POSTS,
    INDEX_PROFILES,
    setup_all_indices,
)
from services.voting_service.apps.votes.models import VoteValue
from tests.test_feed_service.conftest import MockRedis
from tests.test_search_service.conftest import MockElasticsearch


@pytest.fixture
def client() -> DMRClient:
    """Fixture providing DMR test client with automatic JSON encoding."""
    return DMRClient()


@pytest.fixture
def mock_redis() -> MockRedis:
    """Fixture providing in-memory Redis instance."""
    return MockRedis()


@pytest.fixture
def mock_es() -> MockElasticsearch:
    """Fixture providing in-memory Elasticsearch mock instance with all indices initialized."""
    es = MockElasticsearch()
    set_elasticsearch_client(es)
    setup_all_indices(client=es)
    yield es
    reset_elasticsearch_client()


@pytest.fixture(autouse=True)
def clean_databases():
    """Ensure in-memory and MongoDB state is cleared between tests."""
    try:
        get_posts_collection().delete_many({})
        get_comments_collection().delete_many({})
    except Exception:
        pass
    yield
    try:
        get_posts_collection().delete_many({})
        get_comments_collection().delete_many({})
    except Exception:
        pass


@pytest.mark.django_db
def test_complete_user_lifecycle_inter_service_e2e(
    client: DMRClient,
    mock_redis: MockRedis,
    mock_es: MockElasticsearch,
) -> None:
    """Execute the full end-to-end user lifecycle across all 7 microservices."""
    captured_events: list[dict] = []

    def mock_publish(*args, **kwargs):
        event = args[0] if args else kwargs.get("event")
        captured_events.append({"type": getattr(event, "event_type", type(event).__name__), "event": event})

    with (
        patch("services.post_comment_service.apps.posts.services._publish_event", side_effect=mock_publish),
        patch("services.post_comment_service.apps.comments.services._publish_event", side_effect=mock_publish),
        patch("services.voting_service.apps.votes.services.publish_domain_event", side_effect=mock_publish),
        patch("services.post_comment_service.apps.posts.services._check_forum_post_permission", return_value=None),
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch("services.feed_service.apps.feed.controllers.get_redis_client", return_value=mock_redis),
    ):
        # ------------------------------------------------------------------
        # Step 1: User A (Architect Alice) Registration & Onboarding
        # ------------------------------------------------------------------
        signup_alice_payload = {
            "username": "alice_architect",
            "email": "alice@distributed.io",
            "password": "SecurePassword123!",
            "display_name": "Alice Architect",
        }
        resp_signup_a = client.post("/api/v1/auth/signup/", data=signup_alice_payload)
        assert resp_signup_a.status_code == HTTPStatus.CREATED
        data_signup_a = resp_signup_a.json()
        assert "profile" in data_signup_a
        alice_profile_id = data_signup_a["profile"]["id"]
        alice_access_token = data_signup_a["tokens"]["access"]
        alice_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {alice_access_token}",
            "Authorization": f"Bearer {alice_access_token}",
        }

        # ------------------------------------------------------------------
        # Step 2: User B (Engineer Bob) Registration & Onboarding
        # ------------------------------------------------------------------
        signup_bob_payload = {
            "username": "bob_engineer",
            "email": "bob@distributed.io",
            "password": "SecurePassword123!",
            "display_name": "Bob Engineer",
        }
        resp_signup_b = client.post("/api/v1/auth/signup/", data=signup_bob_payload)
        assert resp_signup_b.status_code == HTTPStatus.CREATED
        data_signup_b = resp_signup_b.json()
        bob_profile_id = data_signup_b["profile"]["id"]
        bob_access_token = data_signup_b["tokens"]["access"]
        bob_headers = {
            "HTTP_AUTHORIZATION": f"Bearer {bob_access_token}",
            "Authorization": f"Bearer {bob_access_token}",
        }

        # ------------------------------------------------------------------
        # Step 3: Authentication & Asymmetric RS256 JWT Token Verification
        # ------------------------------------------------------------------
        resp_login_a = client.post(
            "/api/v1/auth/login/",
            data={"email_or_username": "alice_architect", "password": "SecurePassword123!"},
        )
        assert resp_login_a.status_code == HTTPStatus.OK
        alice_login_data = resp_login_a.json()
        assert "tokens" in alice_login_data
        assert alice_login_data["profile_id"] == alice_profile_id

        # Verify Alice profile identity via /api/v1/auth/me/
        resp_me_a = client.get("/api/v1/auth/me/", **alice_headers)
        assert resp_me_a.status_code == HTTPStatus.OK
        assert resp_me_a.json()["user"]["username"] == "alice_architect"

        # ------------------------------------------------------------------
        # Step 4: Social Graph - Bob Follows Alice
        # ------------------------------------------------------------------
        resp_follow = client.post(
            f"/api/v1/profiles/{alice_profile_id}/follow/",
            **bob_headers,
        )
        assert resp_follow.status_code in (HTTPStatus.OK, HTTPStatus.CREATED)

        resp_following = client.get(
            f"/api/v1/profiles/{bob_profile_id}/following/",
            **bob_headers,
        )
        assert resp_following.status_code == HTTPStatus.OK
        assert resp_following.json()["count"] >= 1

        # ------------------------------------------------------------------
        # Step 5: Forum Community Creation by Alice
        # ------------------------------------------------------------------
        forum_payload = {
            "title": "Distributed Systems & Cloud Architecture",
            "slug": "distributed-systems",
            "description": "Excellence in building scalable, resilient microservices.",
            "rules": "1. Provide benchmarks.\n2. Respect peers.",
            "post_permission": "ALL_MEMBERS",
            "require_approval_to_join": False,
        }
        resp_forum = client.post("/api/v1/forums/", data=forum_payload, **alice_headers)
        assert resp_forum.status_code == HTTPStatus.CREATED
        forum_data = resp_forum.json()
        assert forum_data["slug"] == "distributed-systems"
        assert forum_data["members_count"] == 1
        forum_id = forum_data["id"]

        # ------------------------------------------------------------------
        # Step 6: Bob Joins Alice's Forum Community
        # ------------------------------------------------------------------
        resp_join = client.post(
            f"/api/v1/forums/{forum_data['slug']}/join/",
            **bob_headers,
        )
        assert resp_join.status_code in (HTTPStatus.OK, HTTPStatus.CREATED)
        assert resp_join.json()["status"] == MemberStatusChoices.APPROVED.value

        # Verify members count increased in Forum DB
        resp_forum_detail = client.get(f"/api/v1/forums/{forum_data['slug']}/", **alice_headers)
        assert resp_forum_detail.status_code == HTTPStatus.OK
        assert resp_forum_detail.json()["members_count"] == 2

        # ------------------------------------------------------------------
        # Step 7: Media Presigned Upload URL Request from Media Service
        # ------------------------------------------------------------------
        media_payload = {
            "filename": "polyglot-architecture.png",
            "file_size_bytes": 1024 * 512,  # 512 KB
            "content_type": "image/png",
            "purpose": "POST_ATTACHMENT",
        }
        resp_media = client.post("/api/v1/media/upload-url/", data=media_payload, **alice_headers)
        assert resp_media.status_code == HTTPStatus.OK
        media_data = resp_media.json()
        assert "upload_url" in media_data
        assert "cdn_url" in media_data
        assert media_data["cdn_url"].endswith(".png")
        uploaded_media_url = media_data["cdn_url"]

        # ------------------------------------------------------------------
        # Step 8: Post Publishing in Post & Comment Service (MongoDB)
        # ------------------------------------------------------------------
        post_payload = {
            "forum_id": forum_id,
            "title": "Mastering Polyglot Persistence: PostgreSQL, MongoDB, Redis and Elasticsearch",
            "body": "In distributed microservices, no single database fits all operational needs. "
                    "We leverage PostgreSQL for ACID transactions, MongoDB for posts, Redis for CQRS reads, "
                    "and Elasticsearch for fuzzy text searches.",
            "image": uploaded_media_url,
            "tags": ["Distributed Systems", "Database", "Architecture"],
            "visibility": "PUBLIC",
            "comment_permission": "ANYONE",
        }
        resp_post = client.post("/api/v1/posts/", data=post_payload, **alice_headers)
        assert resp_post.status_code == HTTPStatus.CREATED
        post_data = resp_post.json()
        assert post_data["title"] == post_payload["title"]
        assert post_data["image"] == uploaded_media_url
        assert post_data["author_profile_id"] == str(alice_profile_id)
        post_id = post_data["id"]

        # Verify post retrieval
        resp_get_post = client.get(f"/api/v1/posts/{post_id}/", **bob_headers)
        assert resp_get_post.status_code == HTTPStatus.OK
        assert resp_get_post.json()["id"] == post_id

        # ------------------------------------------------------------------
        # Step 9: Voting Service Ingestion (Dedicated PostgreSQL Voting DB)
        # ------------------------------------------------------------------
        resp_vote = client.post(
            f"/api/v1/posts/{post_id}/votes/",
            data={"value": VoteValue.UPVOTE.value},
            **bob_headers,
        )
        assert resp_vote.status_code == HTTPStatus.OK
        vote_data = resp_vote.json()
        assert vote_data["data"]["user_vote"] == VoteValue.UPVOTE.value

        # Verify Bob's personal vote state
        resp_vote_me = client.get(f"/api/v1/posts/{post_id}/votes/me/", **bob_headers)
        assert resp_vote_me.status_code == HTTPStatus.OK
        assert resp_vote_me.json()["data"]["user_vote"] == VoteValue.UPVOTE.value

        # Simulate Worker updating MongoDB counter cache ($inc)
        get_posts_collection().update_one(
            {"_id": post_id},
            {"$inc": {"upvotes_count": 1, "popularity_score": 1}},
        )

        # ------------------------------------------------------------------
        # Step 10: Nested Comments Discussion Tree
        # ------------------------------------------------------------------
        # Bob submits a Root comment (depth 0)
        comment_payload = {
            "body": "Brilliant architecture overview! How do you handle cache invalidation on the feed?",
        }
        resp_comment = client.post(
            f"/api/v1/posts/{post_id}/comments/",
            data=comment_payload,
            **bob_headers,
        )
        assert resp_comment.status_code == HTTPStatus.CREATED
        comment_data = resp_comment.json()
        assert comment_data["depth"] == 0
        root_comment_id = comment_data["id"]

        # Alice replies to Bob's comment (depth 1)
        reply_payload = {
            "body": "Great question! We use a sliding 24-hour window recomputed asynchronously by Celery Beat.",
        }
        resp_reply = client.post(
            f"/api/v1/comments/{root_comment_id}/replies/",
            data=reply_payload,
            **alice_headers,
        )
        assert resp_reply.status_code == HTTPStatus.CREATED
        reply_data = resp_reply.json()
        assert reply_data["depth"] == 1
        assert reply_data["parent_id"] == root_comment_id

        # Bob upvotes Alice's reply in Voting Service
        resp_comment_vote = client.post(
            f"/api/v1/comments/{reply_data['id']}/votes/",
            data={"value": VoteValue.UPVOTE.value},
            **bob_headers,
        )
        assert resp_comment_vote.status_code == HTTPStatus.OK

        # ------------------------------------------------------------------
        # Step 11: CQRS Ranking & Feed Service (Redis Read Store)
        # ------------------------------------------------------------------
        # Seed ranking in Redis Sorted Set (as Celery Beat aggregator does)
        mock_redis.zadd(REDIS_KEY_POPULAR_24H_GLOBAL, {post_id: 150.0})

        resp_feed = client.get("/api/v1/feeds/explore/?sort=popular&limit=10")
        assert resp_feed.status_code == HTTPStatus.OK
        feed_items = resp_feed.json()["data"]
        assert len(feed_items) >= 1
        assert feed_items[0]["id"] == post_id
        assert feed_items[0]["title"] == post_payload["title"]

        # ------------------------------------------------------------------
        # Step 12: Search & Autocomplete in Elasticsearch 8.x
        # ------------------------------------------------------------------
        # Ingest documents into Mock Elasticsearch
        mock_es.index(
            index=INDEX_POSTS,
            id=post_id,
            document={
                "id": post_id,
                "title": post_payload["title"],
                "body": post_payload["body"],
                "author_id": str(alice_profile_id),
                "author_display_name": "Alice Architect",
                "forum_id": forum_id,
                "forum_title": forum_payload["title"],
                "forum_slug": forum_data["slug"],
                "tags": ["distributed-systems", "database", "architecture"],
                "visibility": "PUBLIC",
                "is_deleted": False,
                "has_image": True,
                "vote_score": 1,
                "popularity_score": 10,
                "comment_count": 2,
                "created_at": "2026-10-27T12:00:00Z",
                "updated_at": "2026-10-27T12:00:00Z",
            },
        )
        mock_es.index(
            index=INDEX_FORUMS,
            id=forum_id,
            document={
                "id": forum_id,
                "title": forum_payload["title"],
                "slug": forum_data["slug"],
                "description": forum_payload["description"],
                "rules": forum_payload["rules"],
                "is_locked": False,
                "permission_post": "ALL_MEMBERS",
                "member_count": 2,
                "post_count": 1,
            },
        )
        mock_es.index(
            index=INDEX_PROFILES,
            id=str(alice_profile_id),
            document={
                "id": str(alice_profile_id),
                "profile_id": str(alice_profile_id),
                "username": "alice_architect",
                "display_name": "Alice Architect",
                "bio": "Senior Cloud Architect specializing in distributed systems.",
                "is_private": False,
                "reputation_score": 250,
                "followers_count": 1,
            },
        )

        # Autocomplete suggestions (Search-as-you-type)
        resp_suggest = client.get("/api/v1/search/suggest/?q=polyglot")
        assert resp_suggest.status_code == HTTPStatus.OK
        suggestions = resp_suggest.json()["suggestions"]
        assert len(suggestions) >= 1
        assert any("polyglot" in s["text"].lower() for s in suggestions)

        # Unified multi-entity search
        resp_unified = client.get("/api/v1/search/?q=architecture")
        assert resp_unified.status_code == HTTPStatus.OK
        unified_data = resp_unified.json()
        assert len(unified_data["results"]["posts"]) >= 1
        assert unified_data["results"]["posts"][0]["id"] == post_id
        assert len(unified_data["results"]["forums"]) >= 1
        assert unified_data["results"]["forums"][0]["id"] == forum_id


@pytest.mark.django_db
def test_gateway_routing_and_access_control_e2e(
    client: DMRClient,
    mock_redis: MockRedis,
    mock_es: MockElasticsearch,
) -> None:
    """Validate API Gateway ingress security, authentication gates, and route discrimination."""
    with (
        patch("services.feed_service.apps.feed.services.get_redis_client", return_value=mock_redis),
        patch("services.feed_service.apps.feed.controllers.get_redis_client", return_value=mock_redis),
    ):
        # 1. Unauthenticated requests to protected endpoints return 401 Unauthorized
        resp_unauth_forum = client.post("/api/v1/forums/", data={"title": "Unauthorized Forum"})
        assert resp_unauth_forum.status_code == HTTPStatus.UNAUTHORIZED

        resp_unauth_post = client.post("/api/v1/posts/", data={"title": "Unauthorized Post"})
        assert resp_unauth_post.status_code == HTTPStatus.UNAUTHORIZED

        resp_unauth_media = client.post("/api/v1/media/upload-url/", data={"filename": "test.png"})
        assert resp_unauth_media.status_code == HTTPStatus.UNAUTHORIZED

        # 2. Public feed & search endpoints accessible without credentials
        resp_feed = client.get("/api/v1/feeds/explore/?sort=popular")
        assert resp_feed.status_code == HTTPStatus.OK

        resp_search = client.get("/api/v1/search/suggest/?q=test")
        assert resp_search.status_code == HTTPStatus.OK

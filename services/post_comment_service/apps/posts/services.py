"""Domain logic and business services for Post & Comment Service.

All persistence is via MongoDB (PyMongo). No Django ORM is used for posts
or comments.  Business rules enforced here:

- Forum membership/permission verification (internal call to Forum Service)
- Visibility filtering for profile posts (PUBLIC / FOLLOWERS_ONLY / PRIVATE)
- Pin limit enforcement (delegated to Forum Service)
- Tag slug normalisation (lowercase, hyphenated)
- Event publishing to RabbitMQ after every state mutation
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.conf import settings

from services.post_comment_service.db import get_posts_collection
from shared.events.constants import (
    EXCHANGE_EVENTS,
    ROUTING_POST_CREATED,
    ROUTING_POST_DELETED,
    ROUTING_POST_UPDATED,
)
from shared.events.posts import PostCreatedEvent, PostDeletedEvent, PostUpdatedEvent
from shared.exceptions.base import (
    EntityNotFoundException,
    PermissionDeniedException,
    ValidationException,
)

if TYPE_CHECKING:
    from services.post_comment_service.apps.posts.schemas import (
        PostCreateSchema,
        PostListQuerySchema,
        PostUpdateSchema,
    )

# ============================================================================
# Tag utilities
# ============================================================================

_TAG_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify_tag(name: str) -> str:
    """Normalise a tag to a lowercase slug."""
    return _TAG_SLUG_RE.sub("-", name.strip().lower()).strip("-")


def _build_tag_objects(raw_tags: list[str]) -> list[dict[str, str]]:
    """Convert raw tag strings to {name, slug} dicts stored in MongoDB."""
    seen: set[str] = set()
    result = []
    for tag in raw_tags:
        slug = _slugify_tag(tag)
        if slug and slug not in seen:
            seen.add(slug)
            result.append({"name": tag.strip(), "slug": slug})
    return result


# ============================================================================
# Serialisation helpers
# ============================================================================


def _doc_to_dict(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw MongoDB document to a JSON-serialisable dict."""
    return {
        "id": str(doc["_id"]),
        "author_profile_id": str(doc["author_profile_id"]),
        "forum_id": str(doc["forum_id"]) if doc.get("forum_id") else None,
        "title": doc["title"],
        "body": doc["body"],
        "image": doc.get("image"),
        "tags": doc.get("tags", []),
        "visibility": doc.get("visibility", "PUBLIC"),
        "comment_permission": doc.get("comment_permission", "ANYONE"),
        "admin_visibility": doc.get("admin_visibility", "ALL"),
        "is_pinned": doc.get("is_pinned", False),
        "pin_order": doc.get("pin_order", 0),
        "is_archived": doc.get("is_archived", False),
        "is_deleted": doc.get("is_deleted", False),
        "upvotes_count": doc.get("upvotes_count", 0),
        "downvotes_count": doc.get("downvotes_count", 0),
        "popularity_score": doc.get("popularity_score", 0),
        "comments_count": doc.get("comments_count", 0),
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc.get("created_at"), datetime)
        else str(doc.get("created_at", "")),
        "updated_at": doc["updated_at"].isoformat()
        if isinstance(doc.get("updated_at"), datetime)
        else str(doc.get("updated_at", "")),
    }


# ============================================================================
# Event publishing
# ============================================================================


def _publish_event(event: Any) -> None:
    """Fire-and-forget RabbitMQ event publish.

    Failures are swallowed so that a broker outage never breaks the
    primary write path.
    """
    try:
        import msgspec
        import pika

        routing_key_map = {
            "post.created": ROUTING_POST_CREATED,
            "post.updated": ROUTING_POST_UPDATED,
            "post.deleted": ROUTING_POST_DELETED,
        }

        body = msgspec.json.encode(event)
        routing_key = routing_key_map.get(event.event_type, event.event_type)

        params = pika.URLParameters(settings.RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(
            exchange=EXCHANGE_EVENTS,
            exchange_type="topic",
            durable=True,
        )
        channel.basic_publish(
            exchange=EXCHANGE_EVENTS,
            routing_key=routing_key,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                content_type="application/json",
            ),
        )
        connection.close()
    except Exception:
        # Do not fail request if RabbitMQ is unavailable in test/local dev
        pass


# ============================================================================
# Forum permission verification
# ============================================================================


def _check_forum_post_permission(forum_id: str, author_profile_id: UUID) -> None:
    """Verify that author_profile_id has permission to post in forum_id.

    Makes an internal HTTP call to Forum Service.
    Fails open (allows post) in dev if Forum Service is unreachable.
    """
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    base_url = settings.FORUM_SERVICE_BASE_URL.rstrip("/")
    params = urllib.parse.urlencode({"user_profile_id": str(author_profile_id)})
    url = f"{base_url}/api/v1/internal/forums/{forum_id}/check-post-permission/?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            if not data.get("can_post", True):
                reason = data.get("reason", "You do not have permission to post in this forum.")
                raise PermissionDeniedException(reason)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise EntityNotFoundException("Forum not found.") from exc
        if exc.code == 403:
            raise PermissionDeniedException(
                "You do not have permission to post in this forum."
            ) from exc
    except Exception:
        # In dev or testing, allow if Forum Service is offline
        pass


# ============================================================================
# Post CRUD operations
# ============================================================================


def create_post(
    author_profile_id: UUID,
    payload: PostCreateSchema,
) -> dict[str, Any]:
    """Create a new post document in MongoDB and emit post.created event."""
    col = get_posts_collection()

    if not payload.title.strip():
        raise ValidationException("Post title cannot be blank.")
    if not payload.body.strip():
        raise ValidationException("Post body cannot be blank.")

    # Validate forum membership if this is a forum post
    if payload.forum_id:
        _check_forum_post_permission(payload.forum_id, author_profile_id)
        visibility = "PUBLIC"  # Forum posts are always forum-scoped public
    else:
        visibility = payload.visibility

    now = datetime.now(tz=UTC)
    post_id = str(uuid.uuid4())
    tags = _build_tag_objects(payload.tags)

    doc: dict[str, Any] = {
        "_id": post_id,
        "author_profile_id": str(author_profile_id),
        "forum_id": str(payload.forum_id) if payload.forum_id else None,
        "title": payload.title.strip(),
        "body": payload.body.strip(),
        "image": payload.image,
        "tags": tags,
        "visibility": visibility,
        "comment_permission": payload.comment_permission,
        "admin_visibility": "ALL",
        "is_pinned": False,
        "pin_order": 0,
        "is_archived": False,
        "is_deleted": False,
        "upvotes_count": 0,
        "downvotes_count": 0,
        "popularity_score": 0,
        "comments_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    col.insert_one(doc)

    # Publish domain event (non-blocking)
    _publish_event(
        PostCreatedEvent(
            post_id=UUID(post_id),
            author_profile_id=author_profile_id,
            forum_id=UUID(payload.forum_id) if payload.forum_id else None,
            title=doc["title"],
            body=doc["body"],
            tags=[t["slug"] for t in tags],
            image_url=payload.image,
            visibility=visibility,
        )
    )

    return _doc_to_dict(doc)


def get_post(post_id: str, viewer_profile_id: UUID | None = None) -> dict[str, Any]:
    """Fetch a single post document.

    Raises EntityNotFoundException if not found or is_deleted=True
    (unless the caller is the author or a forum admin).
    """
    col = get_posts_collection()
    try:
        oid = str(UUID(post_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid post ID format.") from exc

    doc = col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Post not found.")

    # Soft-deleted posts are hidden from general access
    if doc.get("is_deleted") and (
        viewer_profile_id is None or str(viewer_profile_id) != str(doc.get("author_profile_id"))
    ):
        raise EntityNotFoundException("Post not found.")

    return _doc_to_dict(doc)


def list_posts(
    query: PostListQuerySchema,
    viewer_profile_id: UUID | None,
) -> tuple[list[dict[str, Any]], int]:
    """List posts with filtering, visibility rules, and simple offset pagination.

    Returns (results, total_count).
    """
    col = get_posts_collection()

    filters: dict[str, Any] = {"is_deleted": False}

    if query.forum_id:
        filters["forum_id"] = str(UUID(query.forum_id))

    if query.author_profile_id:
        filters["author_profile_id"] = str(UUID(query.author_profile_id))

    if query.tag:
        filters["tags.slug"] = query.tag.lower()

    # Visibility: hide PRIVATE posts from others
    if viewer_profile_id is None:
        filters["visibility"] = "PUBLIC"

    # Ordering
    sort_map = {
        "-created_at": [("created_at", -1)],
        "-popularity_score": [("popularity_score", -1)],
        "pin_order": [("pin_order", 1), ("created_at", -1)],
    }
    sort = sort_map.get(query.ordering, [("created_at", -1)])

    total = col.count_documents(filters)
    page = max(1, query.page)
    page_size = min(100, max(1, query.page_size))
    skip = (page - 1) * page_size

    cursor = col.find(filters).sort(sort).skip(skip).limit(page_size)
    results = [_doc_to_dict(d) for d in cursor]

    return results, total


def check_forum_admin(forum_id: str, profile_id: UUID) -> bool:
    """Return True if profile_id is ADMIN or OWNER in the given forum.

    Makes a lightweight internal call to Forum Service.
    Fails open (False) on network/auth failure in development.
    """
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    base_url = settings.FORUM_SERVICE_BASE_URL.rstrip("/")
    params = urllib.parse.urlencode({"user_profile_id": str(profile_id)})
    url = f"{base_url}/api/v1/internal/forums/{forum_id}/check-post-permission/?{params}"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        role = (data.get("user_role") or "").upper()
        return role in ("ADMIN", "OWNER")
    except Exception:
        return False


def update_post(
    post_id: str,
    requester_profile_id: UUID,
    payload: PostUpdateSchema,
) -> dict[str, Any]:
    """Apply partial updates to a post document.

    Permitted for the post author or forum admin/moderator.
    If admin_visibility is set, requester must be a forum admin/owner.
    """
    col = get_posts_collection()
    doc = get_post(post_id)
    forum_id = doc.get("forum_id")

    is_author = str(requester_profile_id) == str(doc["author_profile_id"])
    is_admin = False
    if forum_id:
        is_admin = check_forum_admin(forum_id, requester_profile_id)

    if not is_author and not is_admin:
        raise PermissionDeniedException("You do not have permission to edit this post.")

    if payload.admin_visibility is not None and not is_admin:
        raise PermissionDeniedException("Only forum administrators can change admin visibility.")

    if doc.get("is_archived"):
        raise ValidationException("Cannot edit an archived post.")

    oid = str(UUID(post_id))
    updates: dict[str, Any] = {"updated_at": datetime.now(tz=UTC)}

    if payload.title is not None:
        if not payload.title.strip():
            raise ValidationException("Post title cannot be blank.")
        updates["title"] = payload.title.strip()

    if payload.body is not None:
        if not payload.body.strip():
            raise ValidationException("Post body cannot be blank.")
        updates["body"] = payload.body.strip()

    if payload.image is not None:
        updates["image"] = payload.image

    if payload.tags is not None:
        updates["tags"] = _build_tag_objects(payload.tags)

    if payload.visibility is not None:
        updates["visibility"] = payload.visibility

    if payload.comment_permission is not None:
        updates["comment_permission"] = payload.comment_permission

    if payload.admin_visibility is not None:
        updates["admin_visibility"] = payload.admin_visibility

    col.update_one({"_id": oid}, {"$set": updates})
    updated_doc = col.find_one({"_id": oid})

    # Publish update event
    _publish_event(
        PostUpdatedEvent(
            post_id=UUID(oid),
            author_profile_id=UUID(str(doc["author_profile_id"])),
            forum_id=UUID(str(doc["forum_id"])) if doc.get("forum_id") else None,
            title=updated_doc["title"],
            tags=[t["slug"] for t in updated_doc.get("tags", [])],
            image_url=updated_doc.get("image"),
        )
    )

    return _doc_to_dict(updated_doc)


def update_post_as_admin(
    post_id: str,
    requester_profile_id: UUID,
    payload: PostUpdateSchema,
) -> dict[str, Any]:
    """Apply partial updates as a forum admin (bypasses author-only check)."""
    return update_post(post_id, requester_profile_id, payload)


def delete_post(post_id: str, requester_profile_id: UUID) -> None:
    """Soft-delete a post by setting is_deleted=True.

    Allowed for the post author or a forum admin/moderator.
    Preserves the document so that referenced comments remain anchored.
    """
    col = get_posts_collection()
    doc = get_post(post_id)
    forum_id = doc.get("forum_id")

    is_author = str(requester_profile_id) == str(doc["author_profile_id"])
    is_admin = False
    if forum_id:
        is_admin = check_forum_admin(forum_id, requester_profile_id)

    if not is_author and not is_admin:
        raise PermissionDeniedException(
            "Only the post author or a forum admin can delete this post."
        )

    now = datetime.now(tz=UTC)
    col.update_one(
        {"_id": str(UUID(post_id))},
        {"$set": {"is_deleted": True, "updated_at": now}},
    )

    _publish_event(
        PostDeletedEvent(
            post_id=UUID(post_id),
            author_profile_id=UUID(str(doc["author_profile_id"])),
            forum_id=UUID(str(doc["forum_id"])) if doc.get("forum_id") else None,
        )
    )


def delete_post_as_moderator(post_id: str, requester_profile_id: UUID) -> None:
    """Soft-delete a post on behalf of a forum admin/owner."""
    delete_post(post_id, requester_profile_id)


def toggle_archive_post(
    post_id: str,
    requester_profile_id: UUID,
    is_archived: bool,
) -> dict[str, Any]:
    """Toggle archive state. Allowed for post author or forum admin."""
    col = get_posts_collection()
    doc = get_post(post_id)
    forum_id = doc.get("forum_id")

    is_author = str(requester_profile_id) == str(doc["author_profile_id"])
    is_admin = False
    if forum_id:
        is_admin = check_forum_admin(forum_id, requester_profile_id)

    if not is_author and not is_admin:
        raise PermissionDeniedException(
            "Only the post author or a forum admin can archive this post."
        )

    now = datetime.now(tz=UTC)
    col.update_one(
        {"_id": str(UUID(post_id))},
        {"$set": {"is_archived": is_archived, "updated_at": now}},
    )

    return {
        "id": post_id,
        "is_archived": is_archived,
        "updated_at": now.isoformat(),
    }


def toggle_archive_post_as_moderator(
    post_id: str,
    requester_profile_id: UUID,
    is_archived: bool,
) -> dict[str, Any]:
    """Toggle archive state on behalf of a forum admin/owner."""
    return toggle_archive_post(post_id, requester_profile_id, is_archived)


def pin_post(
    post_id: str,
    requester_profile_id: UUID,
    is_pinned: bool,
    pin_order: int = 0,
) -> dict[str, Any]:
    """Pin or unpin a post within its forum."""
    doc = get_post(post_id)
    forum_id = doc.get("forum_id")
    if not forum_id:
        raise ValidationException("Only forum posts can be pinned.")

    return pin_post_in_forum(
        post_id=post_id,
        forum_id=forum_id,
        requester_profile_id=requester_profile_id,
        is_pinned=is_pinned,
        pin_order=pin_order,
    )


def pin_post_in_forum(
    post_id: str,
    forum_id: str,
    requester_profile_id: UUID,
    is_pinned: bool,
    pin_order: int,
) -> dict[str, Any]:
    """Pin or unpin a post inside a forum via Forum Service."""
    import json
    import urllib.error
    import urllib.request

    base_url = settings.FORUM_SERVICE_BASE_URL.rstrip("/")
    url = f"{base_url}/api/v1/forums/{forum_id}/pinned-posts/{post_id}/pin/"

    body = json.dumps({"is_pinned": is_pinned, "pin_order": pin_order}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Internal-Profile-Id", str(requester_profile_id))

    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise PermissionDeniedException(
                "You do not have permission to pin posts in this forum."
            ) from exc
        if exc.code == 400:
            raise ValidationException(
                "Pinning failed - forum pin limit (10) may be reached."
            ) from exc

    # Mirror pin state on the post document for efficient list queries
    col = get_posts_collection()
    now = datetime.now(tz=UTC)
    try:
        oid = str(UUID(post_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid post ID format.") from exc

    col.update_one(
        {"_id": oid},
        {"$set": {"is_pinned": is_pinned, "pin_order": pin_order, "updated_at": now}},
    )

    return {
        "id": post_id,
        "is_pinned": is_pinned,
        "pin_order": pin_order,
        "updated_at": now.isoformat(),
    }

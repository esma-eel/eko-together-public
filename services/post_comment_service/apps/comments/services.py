"""Domain logic and business services for Comment Service.

All persistence is via MongoDB (PyMongo). Business rules enforced here:
- Strict 3-tier depth cap: depth is 0 (root), 1, 2, or 3.
  Parent.depth >= 3 -> raises ValidationException (HTTP 400).
- Tree-preserving soft delete:
  * If comment has child replies -> body becomes '[deleted]', author info hidden.
  * If leaf comment -> marked deleted.
- Comment permission validation against parent post:
  * post.is_deleted or post.is_archived -> forbidden
  * post.comment_permission == "NO_ONE" -> forbidden
- Inline vote tracking (_votes dictionary on document) in Phase 4.
  Offloaded to Voting Service in Phase 5.
- Event publishing to RabbitMQ after comment creation, update, and deletion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from django.conf import settings

from services.post_comment_service.db import (
    get_comments_collection,
    get_posts_collection,
)
from shared.events.constants import (
    EXCHANGE_EVENTS,
    ROUTING_COMMENT_CREATED,
    ROUTING_COMMENT_DELETED,
    ROUTING_COMMENT_UPDATED,
)
from shared.events.posts import (
    CommentCreatedEvent,
    CommentDeletedEvent,
    CommentUpdatedEvent,
)
from shared.exceptions.base import (
    EntityNotFoundException,
    PermissionDeniedException,
    ValidationException,
)

MAX_DEPTH = 3


# ============================================================================
# Event publishing
# ============================================================================


def _publish_event(event: Any) -> None:
    """Fire-and-forget RabbitMQ event publish."""
    try:
        import msgspec
        import pika

        routing_key_map = {
            "comment.created": ROUTING_COMMENT_CREATED,
            "comment.updated": ROUTING_COMMENT_UPDATED,
            "comment.deleted": ROUTING_COMMENT_DELETED,
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
        pass


def _count_children(comment_id: str) -> int:
    """Count direct child replies for a given comment."""
    col = get_comments_collection()
    return col.count_documents({"parent_id": str(comment_id)})


def _doc_to_dict(doc: dict[str, Any], user_votes: dict | None = None) -> dict[str, Any]:
    """Convert raw MongoDB comment document to a JSON-serialisable dict."""
    comment_id = str(doc["_id"])
    author_id = doc.get("author_profile_id")
    is_deleted = doc.get("is_deleted", False)

    return {
        "id": comment_id,
        "post_id": str(doc["post_id"]),
        "parent_id": str(doc["parent_id"]) if doc.get("parent_id") else None,
        "depth": doc.get("depth", 0),
        "author": {
            "id": str(author_id) if author_id and not is_deleted else None,
            "display_name": doc.get("author_display_name") if not is_deleted else None,
            "avatar": doc.get("author_avatar") if not is_deleted else None,
        },
        "body": "[deleted]" if is_deleted else doc.get("body", ""),
        "upvotes_count": doc.get("upvotes_count", 0),
        "downvotes_count": doc.get("downvotes_count", 0),
        "popularity_score": doc.get("popularity_score", 0),
        "user_vote": (user_votes or {}).get(comment_id),
        "is_archived": doc.get("is_archived", False),
        "is_deleted": is_deleted,
        "replies_count": doc.get("replies_count", 0),
        "replies": [],  # filled in by the listing function
        "created_at": doc["created_at"].isoformat()
        if isinstance(doc.get("created_at"), datetime)
        else str(doc.get("created_at", "")),
        "updated_at": doc["updated_at"].isoformat()
        if isinstance(doc.get("updated_at"), datetime)
        else str(doc.get("updated_at", "")),
    }


def _get_post_doc(post_id: str) -> dict[str, Any]:
    """Fetch the post document. Raises EntityNotFoundException if missing."""
    posts_col = get_posts_collection()
    try:
        oid = str(UUID(post_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid post ID format.") from exc
    doc = posts_col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Post not found.")
    return doc


def _validate_can_comment(post_doc: dict[str, Any]) -> None:
    """Raise PermissionDeniedException if commenting is not allowed on this post."""
    if post_doc.get("is_deleted"):
        raise PermissionDeniedException("Cannot comment on a deleted post.")
    if post_doc.get("is_archived"):
        raise PermissionDeniedException("Cannot comment on an archived post.")
    perm = post_doc.get("comment_permission", "ANYONE")
    if perm == "NO_ONE":
        raise PermissionDeniedException("The author has disabled comments on this post.")


# ============================================================================
# Comment CRUD operations
# ============================================================================


def create_root_comment(
    post_id: str,
    author_profile_id: UUID,
    body: str,
    author_display_name: str = "",
    author_avatar: str | None = None,
) -> dict[str, Any]:
    """Insert a root-level comment (depth=0) on a post.

    Validates post existence, archive state, and comment_permission.
    Increments the post's comments_count counter atomically.
    """
    if not body.strip():
        raise ValidationException("Comment body cannot be blank.")

    post_doc = _get_post_doc(post_id)
    _validate_can_comment(post_doc)

    col = get_comments_collection()
    posts_col = get_posts_collection()

    now = datetime.now(tz=UTC)
    comment_id = str(uuid.uuid4())
    post_uuid = str(UUID(post_id))

    doc: dict[str, Any] = {
        "_id": comment_id,
        "post_id": post_uuid,
        "parent_id": None,
        "depth": 0,
        "author_profile_id": str(author_profile_id),
        "author_display_name": author_display_name,
        "author_avatar": author_avatar,
        "body": body.strip(),
        "upvotes_count": 0,
        "downvotes_count": 0,
        "popularity_score": 0,
        "is_archived": False,
        "is_deleted": False,
        "replies_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    col.insert_one(doc)

    # Increment post.comments_count
    posts_col.update_one({"_id": post_uuid}, {"$inc": {"comments_count": 1}})

    _publish_event(
        CommentCreatedEvent(
            comment_id=UUID(comment_id),
            post_id=UUID(post_uuid),
            user_profile_id=author_profile_id,
            parent_id=None,
            depth=0,
        )
    )

    return _doc_to_dict(doc)


def create_reply(
    parent_comment_id: str,
    author_profile_id: UUID,
    body: str,
    author_display_name: str = "",
    author_avatar: str | None = None,
) -> dict[str, Any]:
    """Insert a reply to an existing comment, enforcing 3-tier depth cap.

    Depth cap enforcement:
        - parent.depth must be < MAX_DEPTH (3)
        - new comment depth = parent.depth + 1

    If parent.depth >= 3 -> raise ValidationException (HTTP 400).
    """
    if not body.strip():
        raise ValidationException("Reply body cannot be blank.")

    col = get_comments_collection()
    posts_col = get_posts_collection()

    try:
        parent_oid = str(UUID(parent_comment_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid parent comment ID format.") from exc

    parent_doc = col.find_one({"_id": parent_oid})
    if parent_doc is None:
        raise EntityNotFoundException("Parent comment not found.")

    if parent_doc.get("is_archived"):
        raise PermissionDeniedException("Cannot reply to an archived comment thread.")

    parent_depth = parent_doc.get("depth", 0)
    if parent_depth >= MAX_DEPTH:
        exc = ValidationException(
            f"MAX_DEPTH_EXCEEDED: Comments cannot be nested more than "
            f"{MAX_DEPTH} levels deep (0 to {MAX_DEPTH}).",
            code="MAX_DEPTH_EXCEEDED",
        )
        exc.status_code = 400
        raise exc

    # Validate parent post
    post_id = str(parent_doc["post_id"])
    post_doc = posts_col.find_one({"_id": post_id})
    if post_doc is None or post_doc.get("is_deleted"):
        raise EntityNotFoundException("Post not found.")
    _validate_can_comment(post_doc)

    now = datetime.now(tz=UTC)
    comment_id = str(uuid.uuid4())
    new_depth = parent_depth + 1

    doc: dict[str, Any] = {
        "_id": comment_id,
        "post_id": post_id,
        "parent_id": parent_oid,
        "depth": new_depth,
        "author_profile_id": str(author_profile_id),
        "author_display_name": author_display_name,
        "author_avatar": author_avatar,
        "body": body.strip(),
        "upvotes_count": 0,
        "downvotes_count": 0,
        "popularity_score": 0,
        "is_archived": False,
        "is_deleted": False,
        "replies_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    col.insert_one(doc)

    # Increment parent's replies_count and post's comments_count
    col.update_one({"_id": parent_oid}, {"$inc": {"replies_count": 1}})
    posts_col.update_one({"_id": post_id}, {"$inc": {"comments_count": 1}})

    _publish_event(
        CommentCreatedEvent(
            comment_id=UUID(comment_id),
            post_id=UUID(post_id),
            user_profile_id=author_profile_id,
            parent_id=UUID(parent_oid),
            depth=new_depth,
        )
    )

    return _doc_to_dict(doc)


def list_comments(
    post_id: str,
    ordering: str = "newest",
    page: int = 1,
    page_size: int = 20,
    viewer_profile_id: UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List root-level comments for a post with one-level eager reply fetch."""
    col = get_comments_collection()

    _get_post_doc(post_id)
    post_uuid = str(UUID(post_id))

    sort_map = {
        "popular": [("popularity_score", -1)],
        "newest": [("created_at", -1)],
        "oldest": [("created_at", 1)],
    }
    sort = sort_map.get(ordering, [("created_at", -1)])

    filters = {"post_id": post_uuid, "parent_id": None}
    total = col.count_documents(filters)
    skip = (page - 1) * page_size
    root_docs = list(col.find(filters).sort(sort).skip(skip).limit(page_size))

    root_ids = [d["_id"] for d in root_docs]

    # Eagerly fetch direct children (depth=1)
    if root_ids:
        children_docs = list(col.find({"parent_id": {"$in": root_ids}}).sort([("created_at", 1)]))
    else:
        children_docs = []

    # Map children to parent_id
    children_by_parent: dict[str, list[dict]] = {}
    for child in children_docs:
        pid = str(child["parent_id"])
        children_by_parent.setdefault(pid, []).append(child)

    user_votes: dict[str, int] = {}
    if viewer_profile_id:
        voter_key = str(viewer_profile_id)
        for d in root_docs + children_docs:
            votes = d.get("_votes", {})
            if voter_key in votes:
                user_votes[str(d["_id"])] = votes[voter_key]

    results = []
    for r_doc in root_docs:
        r_dict = _doc_to_dict(r_doc, user_votes)
        child_list = children_by_parent.get(str(r_doc["_id"]), [])
        r_dict["replies"] = [_doc_to_dict(c, user_votes) for c in child_list]
        results.append(r_dict)

    return results, total


def get_comment(comment_id: str) -> dict[str, Any]:
    """Fetch a single comment by ID."""
    col = get_comments_collection()
    try:
        oid = str(UUID(comment_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid comment ID format.") from exc

    doc = col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Comment not found.")
    return _doc_to_dict(doc)


def update_comment(
    comment_id: str,
    requester_profile_id: UUID,
    body: str,
) -> dict[str, Any]:
    """Edit comment text. Author only."""
    if not body.strip():
        raise ValidationException("Comment body cannot be blank.")

    col = get_comments_collection()
    try:
        oid = str(UUID(comment_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid comment ID format.") from exc

    doc = col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Comment not found.")

    if doc.get("is_archived"):
        raise PermissionDeniedException("Cannot edit an archived comment.")

    if str(doc.get("author_profile_id")) != str(requester_profile_id):
        raise PermissionDeniedException("Only the comment author can edit this comment.")

    post_doc = get_posts_collection().find_one({"_id": str(doc["post_id"])})
    if post_doc and post_doc.get("is_archived"):
        raise PermissionDeniedException("Cannot edit a comment on an archived post.")

    now = datetime.now(tz=UTC)
    col.update_one({"_id": oid}, {"$set": {"body": body.strip(), "updated_at": now}})
    updated = col.find_one({"_id": oid})

    _publish_event(
        CommentUpdatedEvent(
            comment_id=UUID(oid),
            post_id=UUID(str(doc["post_id"])),
            user_profile_id=requester_profile_id,
        )
    )

    return _doc_to_dict(updated)


def delete_comment(
    comment_id: str,
    requester_profile_id: UUID,
    is_moderator: bool = False,
) -> None:
    """Soft-delete a comment, preserving the thread tree."""
    col = get_comments_collection()
    posts_col = get_posts_collection()

    try:
        oid = str(UUID(comment_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid comment ID format.") from exc

    doc = col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Comment not found.")

    if not is_moderator and str(doc.get("author_profile_id")) != str(requester_profile_id):
        post_id = str(doc.get("post_id"))
        post_doc = posts_col.find_one({"_id": post_id})
        forum_id = post_doc.get("forum_id") if post_doc else None
        if forum_id:
            from services.post_comment_service.apps.posts.services import check_forum_admin

            if check_forum_admin(forum_id, requester_profile_id):
                is_moderator = True

        if not is_moderator:
            raise PermissionDeniedException(
                "Only the comment author or a forum moderator can delete this comment."
            )

    now = datetime.now(tz=UTC)
    has_children = _count_children(oid) > 0

    if has_children:
        # Preserve tree structure; obscure content only
        col.update_one(
            {"_id": oid},
            {
                "$set": {
                    "is_deleted": True,
                    "body": "[deleted]",
                    "author_profile_id": None,
                    "author_display_name": None,
                    "author_avatar": None,
                    "updated_at": now,
                }
            },
        )
    else:
        col.update_one(
            {"_id": oid},
            {"$set": {"is_deleted": True, "updated_at": now}},
        )

    # Decrement post.comments_count
    posts_col.update_one({"_id": str(doc["post_id"])}, {"$inc": {"comments_count": -1}})

    _publish_event(
        CommentDeletedEvent(
            comment_id=UUID(oid),
            post_id=UUID(str(doc["post_id"])),
        )
    )


def archive_comment(
    comment_id: str,
    requester_profile_id: UUID,
    is_archived: bool,
) -> dict[str, Any]:
    """Archive or un-archive a comment thread."""
    col = get_comments_collection()

    try:
        oid = str(UUID(comment_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid comment ID format.") from exc

    doc = col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Comment not found.")

    now = datetime.now(tz=UTC)
    col.update_one(
        {"_id": oid},
        {"$set": {"is_archived": is_archived, "updated_at": now}},
    )

    updated = col.find_one({"_id": oid})
    return _doc_to_dict(updated)


def vote_on_comment(
    comment_id: str,
    voter_profile_id: UUID,
    value: int,
) -> dict[str, Any]:
    """Cast, flip, or withdraw a vote on a comment."""
    if value not in (-1, 0, 1):
        raise ValidationException("Vote value must be -1, 0, or 1.")

    col = get_comments_collection()
    try:
        oid = str(UUID(comment_id))
    except ValueError as exc:
        raise EntityNotFoundException("Invalid comment ID format.") from exc

    doc = col.find_one({"_id": oid})
    if doc is None:
        raise EntityNotFoundException("Comment not found.")

    if doc.get("is_archived"):
        raise PermissionDeniedException("Cannot vote on an archived comment.")

    voter_str = str(voter_profile_id)
    votes_dict: dict[str, int] = doc.get("_votes") or {}
    prev_vote = votes_dict.get(voter_str, 0)

    if prev_vote == value:
        return {
            "id": oid,
            "upvotes_count": doc.get("upvotes_count", 0),
            "downvotes_count": doc.get("downvotes_count", 0),
            "popularity_score": doc.get("popularity_score", 0),
            "user_vote": value if value != 0 else None,
        }

    up_delta = 0
    down_delta = 0

    if prev_vote == 1:
        up_delta -= 1
    elif prev_vote == -1:
        down_delta -= 1

    if value == 1:
        up_delta += 1
    elif value == -1:
        down_delta += 1

    net_score_delta = (up_delta) - (down_delta)

    now = datetime.now(tz=UTC)
    update_op: dict[str, Any] = {
        "$inc": {
            "upvotes_count": up_delta,
            "downvotes_count": down_delta,
            "popularity_score": net_score_delta,
        },
        "$set": {"updated_at": now},
    }

    if value == 0:
        update_op["$unset"] = {f"_votes.{voter_str}": ""}
    else:
        update_op["$set"][f"_votes.{voter_str}"] = value

    col.update_one({"_id": oid}, update_op)
    updated = col.find_one({"_id": oid})

    return {
        "id": oid,
        "upvotes_count": updated.get("upvotes_count", 0),
        "downvotes_count": updated.get("downvotes_count", 0),
        "popularity_score": updated.get("popularity_score", 0),
        "user_vote": value if value != 0 else None,
    }

"""RabbitMQ event exchange and routing key constants."""

from __future__ import annotations

# Main Topic Exchange
EXCHANGE_EVENTS = "discussion_forum.events"

# Routing Keys
ROUTING_VOTE_CAST = "vote.cast"
ROUTING_VOTE_REVOKED = "vote.revoked"

ROUTING_POST_CREATED = "post.created"
ROUTING_POST_UPDATED = "post.updated"
ROUTING_POST_DELETED = "post.deleted"

ROUTING_COMMENT_CREATED = "comment.created"
ROUTING_COMMENT_UPDATED = "comment.updated"
ROUTING_COMMENT_DELETED = "comment.deleted"

ROUTING_FORUM_CREATED = "forum.created"
ROUTING_FORUM_UPDATED = "forum.updated"
ROUTING_FORUM_DELETED = "forum.deleted"
ROUTING_FORUM_MEMBER_JOINED = "forum.member_joined"
ROUTING_FORUM_MEMBER_LEFT = "forum.member_left"

ROUTING_USER_REGISTERED = "user.registered"
ROUTING_PROFILE_UPDATED = "profile.updated"

# Dedicated Microservice Queues
QUEUE_POST_COUNTERS = "posts.counter_updates"
QUEUE_SEARCH_INGESTION = "search.indexer"
QUEUE_FEED_NOTIFICATIONS = "feed.events"

"""Test settings configuring apps and in-memory database for monorepo test suite."""

from services.auth_user_service.config.settings import *  # noqa: F403

# Ensure in-memory SQLite is used during tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    "voting_db": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

# Install apps from all microservices
INSTALLED_APPS = list(INSTALLED_APPS)  # noqa: F405
if "services.forum_service.apps.forums.apps.ForumsConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.forum_service.apps.forums.apps.ForumsConfig")
if "services.media_service.apps.media.apps.MediaConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.media_service.apps.media.apps.MediaConfig")
if "services.post_comment_service.apps.posts.apps.PostsConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.post_comment_service.apps.posts.apps.PostsConfig")
if "services.post_comment_service.apps.comments.apps.CommentsConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.post_comment_service.apps.comments.apps.CommentsConfig")
if "services.voting_service.apps.votes.apps.VotesConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.voting_service.apps.votes.apps.VotesConfig")
if "services.feed_service.apps.feed.apps.FeedConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.feed_service.apps.feed.apps.FeedConfig")
if "services.search_service.apps.search.apps.SearchConfig" not in INSTALLED_APPS:
    INSTALLED_APPS.append("services.search_service.apps.search.apps.SearchConfig")

ELASTICSEARCH_URL = "http://localhost:9200"
ELASTICSEARCH_TIMEOUT = 5

# RabbitMQ test bypass flag (tests can override or use mocks)
DISABLE_RABBITMQ_FOR_TESTS = True

# MongoDB test settings (in-memory mock)
USE_MONGOMOCK = True
MONGO_URI = "mongomock://localhost"
MONGO_DATABASE = "test_posts_comments_db"

# Media / S3 / MinIO test settings
MINIO_ENDPOINT = "localhost:9000"
MINIO_ROOT_USER = "minio_admin"
MINIO_ROOT_PASSWORD = "minio_password"
MINIO_USE_SSL = False
MINIO_BUCKET_NAME = "forum-media"
MINIO_PUBLIC_URL = "http://localhost:9000/forum-media"
CDN_BASE_URL = "https://cdn.eko-together.com"
S3_REGION_NAME = "us-east-1"

# Point to unified URLconf
ROOT_URLCONF = "tests.test_urls"

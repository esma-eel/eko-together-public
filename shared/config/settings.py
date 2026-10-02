"""Shared typed configuration settings for the distributed system."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Automatically load .env if present
load_dotenv()


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    db: str
    user: str
    password: str

    @property
    def url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class MongoConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def uri(self) -> str:
        if self.user and self.password:
            return f"mongodb://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?authSource=admin"
        return f"mongodb://{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: int
    db: int = 0

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class RabbitMQConfig:
    host: str
    port: int
    management_port: int
    user: str
    password: str

    @property
    def url(self) -> str:
        return f"amqp://{self.user}:{self.password}@{self.host}:{self.port}//"


@dataclass(frozen=True)
class ElasticsearchConfig:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True)
class MinIOConfig:
    endpoint: str
    api_port: int
    console_port: int
    root_user: str
    root_password: str
    use_ssl: bool = False
    bucket_name: str = "forum-media"
    public_url: str = "http://localhost:9000/forum-media"


@dataclass(frozen=True)
class JWTConfig:
    algorithm: str = "RS256"
    access_expiration_minutes: int = 60
    refresh_expiration_days: int = 7
    issuer: str = "eko-together-auth-service"
    audience: str = "eko-together-api"
    private_key_path: Path = Path("keys/private_key.pem")
    public_key_path: Path = Path("keys/public_key.pem")


@dataclass(frozen=True)
class SharedSettings:
    environment: str
    debug: bool
    secret_key: str
    auth_db: PostgresConfig
    forum_db: PostgresConfig
    voting_db: PostgresConfig
    mongo: MongoConfig
    redis: RedisConfig
    rabbitmq: RabbitMQConfig
    elasticsearch: ElasticsearchConfig
    minio: MinIOConfig
    jwt: JWTConfig
    gateway_origin_secret: str = "eko-gateway"


def get_shared_settings() -> SharedSettings:
    """Load configuration values from environment variables with safe defaults."""
    env = os.getenv("ENVIRONMENT", "development")
    debug = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
    secret_key = os.getenv("SECRET_KEY", "dev-insecure-django-secret-key-1234567890")

    auth_db = PostgresConfig(
        host=os.getenv("POSTGRES_AUTH_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_AUTH_PORT", "5432")),
        db=os.getenv("POSTGRES_AUTH_DB", "auth_db"),
        user=os.getenv("POSTGRES_AUTH_USER", "auth_user"),
        password=os.getenv("POSTGRES_AUTH_PASSWORD", "auth_password"),
    )

    forum_db = PostgresConfig(
        host=os.getenv("POSTGRES_FORUM_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_FORUM_PORT", "5433")),
        db=os.getenv("POSTGRES_FORUM_DB", "forum_db"),
        user=os.getenv("POSTGRES_FORUM_USER", "forum_user"),
        password=os.getenv("POSTGRES_FORUM_PASSWORD", "forum_password"),
    )

    voting_db = PostgresConfig(
        host=os.getenv("POSTGRES_VOTING_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_VOTING_PORT", "5434")),
        db=os.getenv("POSTGRES_VOTING_DB", "voting_db"),
        user=os.getenv("POSTGRES_VOTING_USER", "voting_user"),
        password=os.getenv("POSTGRES_VOTING_PASSWORD", "voting_password"),
    )

    mongo = MongoConfig(
        host=os.getenv("MONGO_HOST", "localhost"),
        port=int(os.getenv("MONGO_PORT", "27017")),
        database=os.getenv("MONGO_DATABASE", "posts_comments_db"),
        user=os.getenv("MONGO_INITDB_ROOT_USERNAME", "mongo_admin"),
        password=os.getenv("MONGO_INITDB_ROOT_PASSWORD", "mongo_password"),
    )

    redis = RedisConfig(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
    )

    rabbitmq = RabbitMQConfig(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_AMQP_PORT", "5672")),
        management_port=int(os.getenv("RABBITMQ_MANAGEMENT_PORT", "15672")),
        user=os.getenv("RABBITMQ_DEFAULT_USER", "rabbit_user"),
        password=os.getenv("RABBITMQ_DEFAULT_PASS", "rabbit_password"),
    )

    elasticsearch = ElasticsearchConfig(
        host=os.getenv("ELASTICSEARCH_HOST", "localhost"),
        port=int(os.getenv("ELASTICSEARCH_PORT", "9200")),
    )

    minio = MinIOConfig(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        api_port=int(os.getenv("MINIO_API_PORT", "9000")),
        console_port=int(os.getenv("MINIO_CONSOLE_PORT", "9001")),
        root_user=os.getenv("MINIO_ROOT_USER", "minio_admin"),
        root_password=os.getenv("MINIO_ROOT_PASSWORD", "minio_password"),
        use_ssl=os.getenv("MINIO_USE_SSL", "False").lower() in ("true", "1"),
        bucket_name=os.getenv("MINIO_BUCKET_NAME", "forum-media"),
        public_url=os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000/forum-media"),
    )

    jwt = JWTConfig(
        algorithm=os.getenv("JWT_ALGORITHM", "RS256"),
        access_expiration_minutes=int(os.getenv("JWT_ACCESS_EXPIRATION_MINUTES", "60")),
        refresh_expiration_days=int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", "7")),
        issuer=os.getenv("JWT_ISSUER", "eko-together-auth-service"),
        audience=os.getenv("JWT_AUDIENCE", "eko-together-api"),
        private_key_path=Path(os.getenv("JWT_PRIVATE_KEY_PATH", "keys/private_key.pem")),
        public_key_path=Path(os.getenv("JWT_PUBLIC_KEY_PATH", "keys/public_key.pem")),
    )

    return SharedSettings(
        environment=env,
        debug=debug,
        secret_key=secret_key,
        auth_db=auth_db,
        forum_db=forum_db,
        voting_db=voting_db,
        mongo=mongo,
        redis=redis,
        rabbitmq=rabbitmq,
        elasticsearch=elasticsearch,
        minio=minio,
        jwt=jwt,
        gateway_origin_secret=os.getenv("GATEWAY_ORIGIN_SECRET", "eko-gateway"),
    )

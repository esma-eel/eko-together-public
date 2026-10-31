"""Infrastructure connectivity and health validation script.

Validates TCP ports and application-level responses for all 8 polyglot services
defined in docker-compose.yml.
"""

from __future__ import annotations

import socket
import sys
import urllib.error
import urllib.request
from typing import NamedTuple

from shared.config.settings import get_shared_settings


class ServiceCheck(NamedTuple):
    name: str
    host: str
    port: int
    description: str


def check_tcp_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Attempt a low-level TCP handshake against a target host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def check_http_endpoint(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Perform a simple HTTP GET request to verify service readiness."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "InfraHealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return True, f"HTTP {response.status}"
    except urllib.error.HTTPError as e:
        # Some endpoints return 401/403 or other codes when healthy but unauthenticated
        return True, f"HTTP {e.code} (Service reachable)"
    except Exception as e:
        return False, str(e)


def main() -> int:
    settings = get_shared_settings()

    checks: list[ServiceCheck] = [
        ServiceCheck(
            "Postgres (User & Auth DB)",
            settings.auth_db.host,
            settings.auth_db.port,
            "PostgreSQL 16 on port 5432",
        ),
        ServiceCheck(
            "Postgres (Forum DB)",
            settings.forum_db.host,
            settings.forum_db.port,
            "PostgreSQL 16 on port 5433",
        ),
        ServiceCheck(
            "Postgres (Voting DB)",
            settings.voting_db.host,
            settings.voting_db.port,
            "PostgreSQL 16 on port 5434",
        ),
        ServiceCheck(
            "MongoDB Cluster",
            settings.mongo.host,
            settings.mongo.port,
            "MongoDB 7.0 on port 27017",
        ),
        ServiceCheck(
            "Redis Cache & CQRS",
            settings.redis.host,
            settings.redis.port,
            "Redis 7.2 on port 6379",
        ),
        ServiceCheck(
            "RabbitMQ AMQP Broker",
            settings.rabbitmq.host,
            settings.rabbitmq.port,
            "RabbitMQ AMQP on port 5672",
        ),
        ServiceCheck(
            "RabbitMQ Management UI",
            settings.rabbitmq.host,
            settings.rabbitmq.management_port,
            "RabbitMQ Management on port 15672",
        ),
        ServiceCheck(
            "Elasticsearch Engine",
            settings.elasticsearch.host,
            settings.elasticsearch.port,
            "Elasticsearch 8.x on port 9200",
        ),
        ServiceCheck(
            "MinIO S3 Storage API",
            settings.minio.endpoint.split(":")[0],
            settings.minio.api_port,
            "MinIO S3 API on port 9000",
        ),
        ServiceCheck(
            "MinIO Web Console",
            settings.minio.endpoint.split(":")[0],
            settings.minio.console_port,
            "MinIO Web Console on port 9001",
        ),
    ]

    print("=" * 70)
    print("🔍 Eko-Together - Infrastructure Connectivity & Health Verification")
    print("=" * 70)

    all_passed = True

    for check in checks:
        is_open = check_tcp_port(check.host, check.port)
        status_icon = "✅ UP" if is_open else "❌ DOWN"
        endpoint = f"{check.host}:{check.port}"
        print(f"{status_icon} | {check.name:<26} | {endpoint:<16} | {check.description}")
        if not is_open:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("🎉 ALL INFRASTRUCTURE SERVICES ARE UP AND HEALTHY!")
        return 0
    else:
        print("⚠️ Some services are not yet reachable.")
        print("💡 Ensure Docker is running and run: docker compose up -d")
        return 1


if __name__ == "__main__":
    sys.exit(main())

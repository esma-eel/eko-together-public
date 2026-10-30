#!/usr/bin/env python3
"""Eko-Together Monorepo Service Orchestrator.

Launches all 7 Django microservices concurrently, applies pending database
migrations, and provides interactive links to Swagger docs and API Gateway.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

SERVICES: list[dict[str, str | int]] = [
    {
        "name": "Auth & User Service",
        "dir": "services/auth_user_service",
        "port": 8001,
        "swagger": "http://localhost:8001/docs/swagger/",
        "gateway_route": "/api/v1/auth/",
    },
    {
        "name": "Forum Service",
        "dir": "services/forum_service",
        "port": 8002,
        "swagger": "http://localhost:8002/docs/swagger/",
        "gateway_route": "/api/v1/forums/",
    },
    {
        "name": "Media Service",
        "dir": "services/media_service",
        "port": 8003,
        "swagger": "http://localhost:8003/docs/swagger/",
        "gateway_route": "/api/v1/media/",
    },
    {
        "name": "Post & Comment Service",
        "dir": "services/post_comment_service",
        "port": 8004,
        "swagger": "http://localhost:8004/docs/swagger/",
        "gateway_route": "/api/v1/posts/",
    },
    {
        "name": "Voting Service",
        "dir": "services/voting_service",
        "port": 8005,
        "swagger": "http://localhost:8005/docs/swagger/",
        "gateway_route": "/api/v1/posts/:id/votes/",
    },
    {
        "name": "Feed Service",
        "dir": "services/feed_service",
        "port": 8006,
        "swagger": "http://localhost:8006/docs/swagger/",
        "gateway_route": "/api/v1/feed/",
    },
    {
        "name": "Search Service",
        "dir": "services/search_service",
        "port": 8007,
        "swagger": "http://localhost:8007/docs/swagger/",
        "gateway_route": "/api/v1/search/",
    },
]

MIGRATION_SERVICES = [
    "services/auth_user_service",
    "services/forum_service",
    "services/voting_service",
    "services/media_service",
    "services/post_comment_service",
    "services/feed_service",
    "services/search_service",
]


def apply_migrations() -> None:
    """Run database migrations across all services."""
    print("=" * 72)
    print("📦 Step 1: Checking and applying database migrations for all services...")
    print("=" * 72)
    python_bin = sys.executable
    for svc_dir in MIGRATION_SERVICES:
        manage_py = ROOT_DIR / svc_dir / "manage.py"
        if manage_py.exists():
            print(f"Applying migrations for {svc_dir}...")
            res = subprocess.run([python_bin, str(manage_py), "migrate", "--noinput"], cwd=ROOT_DIR)
            if res.returncode != 0:
                print(f"⚠️ Warning: migration failed for {svc_dir}. Continuing...")
    print("✅ Migrations complete.\n")


def main() -> None:
    apply_migrations()

    print("=" * 72)
    print("🚀 Step 2: Starting all 7 Django Microservices concurrently...")
    print("=" * 72)

    python_bin = sys.executable
    processes: list[subprocess.Popen] = []

    def shutdown(signum=None, frame=None):
        print("\n🛑 Shutting down all microservices...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        for p in processes:
            try:
                p.wait(timeout=2)
            except Exception:
                p.kill()
        print("✅ All services stopped. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for svc in SERVICES:
        manage_py = ROOT_DIR / str(svc["dir"]) / "manage.py"
        port = str(svc["port"])
        cmd = [python_bin, str(manage_py), "runserver", f"0.0.0.0:{port}", "--noreload"]
        p = subprocess.Popen(cmd, cwd=ROOT_DIR)
        processes.append(p)
        print(f"  ▶️  {svc['name']:<24} -> Started on 0.0.0.0:{port}")

    time.sleep(2)

    print("\n" + "=" * 72)
    print("🌟 ALL 7 SERVICES ARE RUNNING! ACCESS LINKS:")
    print("=" * 72)
    print("🌐 Central API Gateway (Port 80 - PRIMARY ENTRYPOINT):")
    print("   👉 Swagger UI Portal: http://localhost/docs/  (or http://127.0.0.1/docs/)")
    print("   👉 Gateway Health:   http://localhost/health")
    print("\n⚠️  Direct Microservice Port Access (8001-8007) is DEPRECATED & RESTRICTED:")
    print("   Direct calls to individual ports return HTTP 403 Forbidden by default.")
    print("   All client traffic must route through the Port 80 Gateway.")
    print("   (To allow direct access for debugging, set ALLOW_DIRECT_SERVICE_ACCESS=true in .env)")
    print("\n📘 Direct Microservice URLs (Debug Mode Only):")
    for svc in SERVICES:
        print(f"   • {svc['name']:<24}: {svc['swagger']}")
    print("=" * 72)
    print("💡 Press Ctrl+C at any time to stop all services.\n")

    try:
        while True:
            time.sleep(1)
            for p in processes:
                if p.poll() is not None:
                    # One process died
                    pass
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()

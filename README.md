# Eko-Together: Distributed Microservices Discussion Forum Platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248.svg?logo=mongodb&logoColor=white)](https://www.mongodb.com/)
[![Redis](https://img.shields.io/badge/Redis-7.2-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600.svg?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-8.15-005571.svg?logo=elasticsearch&logoColor=white)](https://www.elastic.co/)
[![MinIO](https://img.shields.io/badge/MinIO-S3_Compatible-C72C48.svg?logo=minio&logoColor=white)](https://min.io/)
[![Nginx](https://img.shields.io/badge/Nginx-API_Gateway-009639.svg?logo=nginx&logoColor=white)](https://nginx.org/)
[![License](https://img.shields.io/badge/License-All_Rights_Reserved-red.svg)](LICENSE)

A high-performance, event-driven, polyglot-persistence microservices discussion platform inspired by Reddit and Quera. Designed and engineered from the ground up for extreme concurrency, distributed scalability, and domain decoupling.

---

## 👨‍💻 Author & Contact

**Esmaeel Komijani**  
- 🌐 **Personal Website:** [https://esmaeelkomijani.com/](https://esmaeelkomijani.com/)  
- 💼 **LinkedIn Profile:** [https://www.linkedin.com/in/esmaeel-komijani/](https://www.linkedin.com/in/esmaeel-komijani/)  
- 🐙 **GitHub Repository:** [https://github.com/esma-eel/eko-together-public](https://github.com/esma-eel/eko-together-public)  

---

## 🏛️ System Architecture

The platform follows a decoupled, polyglot microservices architecture governed by a unified Nginx API Gateway and asynchronous RabbitMQ event bus:

```
discussion-forum/
├── gateway/                        # Nginx API Gateway & Reverse Proxy (Ingress)
│   ├── nginx.conf                  # Dynamic routing regex, CORS, rate limits & SSL
│   ├── nginx.conf.template         # Environment-aware template
│   ├── Dockerfile                  # Lightweight Alpine container
│   └── static/swagger.html         # Unified Swagger UI multi-spec aggregator
├── services/                       # 7 Independent Domain Microservices
│   ├── auth_user_service/          # RS256 asymmetric auth, user profiles, social graph (PostgreSQL)
│   ├── forum_service/              # Sub-communities, moderation, rules, access tiers (PostgreSQL)
│   ├── media_service/              # S3 Presigned direct-upload allocation & validation (MinIO)
│   ├── post_comment_service/       # Materialized path nested comments & posts (MongoDB)
│   ├── voting_service/             # Ultra-fast atomic voting, Redis counters & event stream (PostgreSQL + RabbitMQ)
│   ├── feed_service/               # CQRS personalized feeds & 24h sliding window ranking (Redis ZSET)
│   └── search_service/             # Multi-entity fuzzy full-text search & search-as-you-type (Elasticsearch)
├── shared/                         # Common shared domain contracts & utilities
│   ├── config/                     # Typed settings loader & environment schema
│   ├── jwt/                        # RS256 signing, public verification & claim extraction
│   ├── exceptions/                 # Standardized domain exceptions & DMR mapping
│   ├── events/                     # Msgspec high-speed serialized domain event schemas & publisher
│   └── middleware/                 # Gateway enforcement middleware (prevents direct port bypass)
├── scripts/                        # Automation & orchestration tooling
│   ├── generate_keys.py            # RSA keypair generation for RS256 JWT
│   ├── run_services.py             # Parallel multi-service orchestrator & auto-migration
│   └── verify_infra.py             # Live health-check & ping probe for all backing stores
├── tests/                          # Automated testing suite (166+ test cases)
│   ├── test_shared/                # Core contracts, JWT & middleware unit tests
│   ├── test_auth_service/          # Auth, RBAC, social graph & audit logging tests
│   ├── test_forum_service/         # Forum CRUD, membership, permissions & pinned posts
│   ├── test_media_service/         # Presigned URL generation & validation tests
│   ├── test_post_comment_service/  # MongoDB posts & materialized nested comment tree tests
│   ├── test_voting_service/        # Concurrent vote tracking, deduplication & consumer tests
│   ├── test_feed_service/          # Sliding-window algorithm & CQRS feed materialization tests
│   ├── test_search_service/        # Elasticsearch indexing, autocomplete & sync tests
│   └── test_e2e/                   # End-to-end user lifecycle integration test
├── docker-compose.yml              # Complete backing infrastructure (7 stateful services + Gateway)
├── pyproject.toml                  # Modern package management via uv
├── .env.example                    # Comprehensive centralized environment configuration
└── keys/                           # RSA public/private cryptographic keypair directory
```

---

## ⚡ Core Technical Highlights

| Component | Technology | Architectural Role |
| :--- | :--- | :--- |
| **API Gateway** | Nginx Reverse Proxy | Unified Port 80 ingress, rate limiting (100r/s auth, 200r/s API), regex routing, CORS, Swagger UI portal |
| **Authentication** | RS256 Asymmetric JWT | Private key signs in Auth Service; downstream services verify using public key without database roundtrips |
| **Nested Comments** | MongoDB Materialized Path | $O(1)$ subtree retrieval for arbitrarily nested comment hierarchies without recursive joins |
| **High-Throughput Voting** | RabbitMQ + PostgreSQL + Redis | Atomic vote ingestion, write-behind counter updates via message broker, sub-millisecond Redis read-through |
| **Personalized Feeds** | CQRS + Redis Sorted Sets (ZSET) | 24-hour sliding time decay algorithm: $Score = \frac{NetVotes}{(AgeInHours + 2)^{1.8}}$ |
| **Full-Text Search** | Elasticsearch 8 | Multi-entity fuzzy matching, prefix edge n-gram autocomplete (`search-as-you-type`), real-time event sync |
| **Media Delivery** | MinIO (S3 Compatible) | Secure presigned direct-to-storage uploads; API servers never handle heavy binary streams |
| **Package Management** | `uv` (Rust-based) | Deterministic, millisecond dependency resolution & execution |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Linux, macOS, or Windows (via WSL2)
- Python 3.12+ (`python3 --version`)
- Docker & Docker Compose (`docker compose version`)
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

---

### 2. Environment & Cryptographic Key Generation

```bash
# 1. Clone repository
git clone https://github.com/esma-eel/eko-together-public.git
cd eko-together-public

# 2. Sync virtual environment and dependencies
uv sync

# 3. Create environment file from template
cp .env.example .env

# 4. Generate RS256 RSA 2048-bit keypair
uv run python scripts/generate_keys.py
```

> **Security Note:** Generated cryptographic keys (`keys/*.pem`) and `.env` files are strictly excluded from version control via `.gitignore`. Only `keys/.gitkeep` and `.env.example` are committed.

---

### 3. Launching Infrastructure & Microservices

#### Step 1: Start Backing Infrastructure (Docker)
```bash
docker compose up -d
```
Verify all containers (Postgres, MongoDB, Redis, RabbitMQ, Elasticsearch, MinIO, Gateway) are healthy:
```bash
uv run python scripts/verify_infra.py
```

#### Step 2: Launch All 7 Microservices (Single Command)
Run database migrations and spawn all 7 microservices concurrently:
```bash
uv run python scripts/run_services.py
```
Each service listens internally on ports `8001` through `8007`.

---

## 📚 Centralized Swagger UI Documentation

All client interaction should be conducted through the **API Gateway (Port 80)**. Direct port access to individual services is restricted in production to enforce security, rate limiting, and centralized auditing.

- 🌐 **Unified Swagger Portal:** **[http://localhost/docs/](http://localhost/docs/)**
- 🏥 **Gateway Health Check:** **[http://localhost/health](http://localhost/health)**

> **Interactive API Testing:** Open the unified portal in your browser, switch between microservice specifications using the top dropdown menu (**Select a definition**), and execute requests using the **Try it out** button directly through the gateway.

### Service Route & Port Breakdown

| Service | Internal Port | Gateway Route Prefix | Primary Data Store |
| :--- | :---: | :--- | :--- |
| **API Gateway** | `80` | `/api/v1/...` | Nginx Ingress |
| **Auth & User Service** | `8001` | `/api/v1/auth/`, `/api/v1/profiles/` | PostgreSQL |
| **Forum Service** | `8002` | `/api/v1/forums/` | PostgreSQL |
| **Media Service** | `8003` | `/api/v1/media/` | MinIO (S3) |
| **Post & Comment Service** | `8004` | `/api/v1/posts/`, `/api/v1/comments/` | MongoDB |
| **Voting Service** | `8005` | `/api/v1/posts/{id}/votes/`, `/api/v1/comments/{id}/votes/` | PostgreSQL + RabbitMQ |
| **Feed & Ranking Service** | `8006` | `/api/v1/feed/` | Redis |
| **Search Service** | `8007` | `/api/v1/search/` | Elasticsearch |

*(Note: To enable direct port debugging without gateway enforcement during local development, set `ALLOW_DIRECT_SERVICE_ACCESS=true` in your `.env` file).*

---

## 🔄 Background Event Consumers

The Voting and Search services run asynchronous RabbitMQ background consumers to process high-volume events out-of-band:

```bash
# Ingest vote events and persist batched counter aggregations
uv run python services/voting_service/manage.py consume_events

# Ingest entity creation/update events and synchronize Elasticsearch indexes
uv run python services/search_service/manage.py consume_events
```

---

## 🧪 Comprehensive Test Suite

The test suite covers unit logic, inter-service contracts, security enforcement, and complete end-to-end user lifecycles:

```bash
# Run all 166+ automated tests
uv run pytest

# Run end-to-end integration test specifically
uv run pytest tests/test_e2e/test_complete_user_lifecycle_e2e.py -v

# Run Newman (Postman CI/CD) automated collection
newman run tests/e2e/discussion_forum_e2e_collection.postman_collection.json \
  -e tests/e2e/discussion_forum_e2e.postman_environment.json
```

---

## 🗺️ Detailed Gateway Endpoint Mapping

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | API Gateway health and uptime check |
| `POST` | `/api/v1/auth/signup/` | Register new user account & receive RS256 JWT tokens |
| `POST` | `/api/v1/auth/login/` | User authentication & token issuance |
| `GET` | `/api/v1/auth/me/` | Retrieve current authenticated user profile |
| `POST` | `/api/v1/profiles/{id}/follow/` | Follow user (social graph relationship) |
| `GET` | `/api/v1/forums/` | List public sub-communities |
| `POST` | `/api/v1/forums/` | Create a new community/forum |
| `POST` | `/api/v1/forums/{slug}/join/` | Join an existing community |
| `POST` | `/api/v1/media/upload-url/` | Generate presigned S3/MinIO direct upload URL |
| `GET` | `/api/v1/posts/` | List posts with pagination and forum filtering |
| `POST` | `/api/v1/posts/` | Publish a new post with optional media attachments |
| `POST` | `/api/v1/posts/{id}/votes/` | Upvote or downvote a post |
| `GET` | `/api/v1/comments/` | Retrieve nested comments via materialized path |
| `POST` | `/api/v1/comments/` | Submit a comment or nested reply |
| `POST` | `/api/v1/comments/{id}/votes/` | Upvote or downvote a comment |
| `GET` | `/api/v1/feed/explore/` | 24-hour trending content feed ranked by decay score |
| `GET` | `/api/v1/feed/following/` | Personalized feed from followed users and joined forums |
| `GET` | `/api/v1/search/suggest/?q=...` | Fast autocomplete search-as-you-type suggestions |
| `GET` | `/api/v1/search/?q=...` | Fuzzy full-text search across posts, forums, and users |

---

## 📈 Development Phases & Milestone Progression

This project was built iteratively across 9 development phases:

- **Phase 0: Shared Core & Infrastructure** — Environment schemas, RS256 JWT cryptographic verification, domain exceptions, message bus schemas with msgspec, Docker Compose setup.
- **Phase 1: Auth & User Service** — PostgreSQL user accounts, password hashing, asymmetric token generation, profile management, and social graph.
- **Phase 2: Forum Service** — Sub-communities, tiered permissions, memberships, and pinned announcements.
- **Phase 3: Media Service** — S3/MinIO presigned URL generator for secure direct binary uploads.
- **Phase 4: Post & Comment Service** — MongoDB schema, post lifecycle, and materialized path hierarchical comment tree.
- **Phase 5: Voting Service** — Decoupled high-velocity voting microservice, atomic deduplication, and RabbitMQ event stream.
- **Phase 6: Feed & Ranking Service** — CQRS read-optimized feeds with Redis Sorted Sets and 24-hour sliding window ranking algorithm.
- **Phase 7: Search Service** — Elasticsearch 8 integration, edge n-gram autocomplete, multi-entity fuzzy search, and event consumer sync.
- **Phase 8: API Gateway & E2E Testing** — Nginx reverse proxy with dynamic regex routing, Swagger UI aggregation portal, rate limiting, and 166-test end-to-end verification.

---

## 📄 License & Intellectual Property

Copyright (c) 2026 **[Esmaeel Komijani](https://esmaeelkomijani.com/)**. All rights reserved.

This repository, source code, and distributed architecture are provided for portfolio showcase, code review, and educational evaluation purposes only. Commercial exploitation, reproduction, resale, sublicensing, or unauthorized redistribution without prior explicit written authorization from the author is strictly prohibited. See [LICENSE](LICENSE) for full legal terms.

Developed with ❤️ by **[Esmaeel Komijani](https://esmaeelkomijani.com/)**.

# Local Deployment Guide

This guide describes how to run and verify JustiAssist locally for development and testing.

## Prerequisites

Before starting, ensure your local environment meets the following requirements:

* **Docker**: Installed and running (Docker Desktop on Windows/Mac).
* **Docker Compose**: Included with Docker Desktop.
* **Git**: For version control.
* **Disk Space**: At least 10GB of free space (for Docker images, PostgreSQL volume, and BGE-M3 model artifacts).
* **RAM**: 16GB+ recommended. The BGE-M3 embedding model and the full in-memory FAISS indices are resource-intensive.

## Environment Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` to configure your environment. 
   **Important Variables:**
   * `APP_ENV`: Leave as `development` for local execution.
   * `GROQ_API_KEY`: Required. Set to your Groq API key (e.g., `gsk_...`).
   * `FIRECRAWL_API_KEY`: Optional, for external evidence fetching.
   * `INDIAN_KANOON_API_KEY`: Optional, for Indian Kanoon search.
   * `JWT_SECRET_KEY`: Can use a dummy value in development, but must be a secure random string in production.
   * `DATABASE_URL`: `postgresql://justiassist:password@postgres:5432/justiassist_db` (preconfigured for Docker).
   * `REDIS_ENABLED`: Optional. `true` to enable Redis rate limiting and caching.

**Security Warning**: Never commit your `.env` file or paste real credentials into GitHub. The browser frontend should never receive backend provider secrets.

## Local Docker Compose Workflow

Follow these steps to run the application using Docker Compose:

### 1. Validate Compose
Verify the compose file configuration without interpolating and printing secrets:
```bash
docker compose config --quiet
```

### 2. Build
Build the backend and frontend containers:
```bash
docker compose build
```

### 3. Start
Start the stack in detached mode:
```bash
docker compose up -d
```

### 4. Status
Check the status of running containers:
```bash
docker compose ps
```

### 5. Logs
View logs for specific services:
```bash
docker compose logs -f backend
docker compose logs -f migrations
docker compose logs -f frontend
docker compose logs -f postgres
docker compose logs -f redis
```

### 6. Stop
Stop the stack without removing persistent volumes:
```bash
docker compose down
```
*(Caution: Do not use `docker compose down -v` unless you intend to permanently delete the persistent PostgreSQL database and local storage volumes).*

## Local Health and Readiness Checks

JustiAssist provides several endpoints to verify system health:

* **`/health/liveness`**: Cheap check to ensure the API process is responsive.
* **`/health/readiness`**: Deep check that verifies the PostgreSQL connection and ensures both the statutory and case-law FAISS indices are fully initialized. Returns `503` if these critical dependencies are not ready.
* **`/health`**: Compatibility endpoint providing detailed status of PostgreSQL, Redis (if enabled), Ollama (if configured), and index availability.

## Local Functional Smoke Test

After running `docker compose up -d`, use this checklist to verify functionality:

### Infrastructure
- [ ] Containers healthy/running (`docker compose ps`)
- [ ] Migrations successful (`docker compose logs migrations`)
- [ ] Backend readiness passes (`curl http://localhost:8000/health/readiness`)
- [ ] Frontend loads (`http://localhost:3000`)

### Authentication
- [ ] Signup a new user
- [ ] Login
- [ ] Perform an authenticated request

### Legal RAG
- [ ] Statutory query returns relevant IPC/BNS sections
- [ ] Case-law query retrieves precedent
- [ ] Hybrid retrieval works properly
- [ ] Citations are present and properly formatted
- [ ] Grounded generation is evident
- [ ] System abstains when asked an unsupported non-legal question

### Documents
- [ ] Upload a document
- [ ] List session documents
- [ ] Query against the uploaded document
- [ ] Download the document
- [ ] Delete/clear session documents

### Streaming
- [ ] SSE query streams correctly
- [ ] SSE authentication works via tickets
- [ ] Disconnecting the client cleans up the active SSE connection

### Security
- [ ] Unauthenticated access to admin/metrics endpoints is rejected
- [ ] Normal user cannot access admin endpoints
- [ ] Logs do not contain raw secrets or PII

### Persistence
- [ ] PostgreSQL data (users, metadata) survives container restart
- [ ] Object storage documents survive container restart
- [ ] *Known Limitation:* Active in-memory DocumentSession state resets upon restart

## Vector Store & BGE-M3 Verification

To verify that the dense retrieval models and indices are properly loaded:
1. Ensure the `vector_stores/` directory exists locally and is mounted.
2. Check backend logs for initialization messages:
   ```bash
   docker compose logs backend | grep -i "loaded successfully"
   ```
3. Use the `/health` endpoint to confirm both `statutory_indexed` and `bail_indexed` are true.
4. You can list the index files without dumping contents using:
   ```bash
   ls -lh vector_stores/
   ```

No index rebuild is required when valid `.index` and metadata artifacts already exist.

## Resource Monitoring

Monitor local resource usage:
* **Docker:**
  ```bash
  docker stats --no-stream
  ```
* **Host:** Ensure Windows Docker Desktop is configured with sufficient memory (Settings > Resources). BGE-M3 and FAISS are the primary memory consumers.

## Testing Guide

The following commands are supported for running tests locally:

**Backend:**
* Run all unit tests:
  ```bash
  python -m pytest
  ```
* Run specific unit tests:
  ```bash
  python -m pytest tests/unit
  ```
* Verify Python syntax:
  ```bash
  python -m compileall .
  ```

**Frontend:**
* Verify frontend build:
  ```bash
  npm run build
  ```
* Run linter:
  ```bash
  npm run lint
  ```

*(Note: Unit tests run isolated via SQLite and do not require Docker services to be up, but depend on a properly configured virtual environment).*

## Database & Migration Guide

JustiAssist uses Alembic for database migrations.
* In Docker Compose, the `migrations` service automatically runs `alembic upgrade head` on startup.
* To check the status of migrations locally:
  ```bash
  alembic check
  ```
* To safely update schema during development, create a new revision and run upgrade, but avoid destroying the PostgreSQL volume (`-v`) unnecessarily.

## Common Troubleshooting

* **BGE-M3 takes time to load:** The model requires significant time and memory to load on the first request or boot. Check logs for progress.
* **Insufficient RAM:** If the backend container exits unexpectedly with code 137, increase Docker memory limits.
* **FAISS index missing:** If `/health/readiness` fails due to missing indices, run the initialization script or trigger `/build-indices`.
* **PostgreSQL not ready:** Ensure the database container is fully started before the backend attempts to connect.
* **Redis unavailable:** Redis is strictly optional. The application will gracefully degrade if Redis cannot be reached.
* **Docker port conflict:** Ensure ports 8000 (backend), 3000 (frontend), 5432 (postgres), and 6379 (redis) are free.
* **Frontend unable to reach backend:** Check CORS `ALLOWED_ORIGINS` in `.env` and ensure the API proxy in `nginx.conf` is correct.
* **SSE issues:** Verify Nginx `proxy_buffering` is off.

# Phase 7F: Docker & Production Deployment Architecture

## Overview
Phase 7F introduces Docker and Docker Compose to JustiAssist to provide a reproducible local development environment and to prepare the application for a production-grade deployment architecture. 

The strategy intentionally avoids baking large stateful components (PostgreSQL, vector assets) or ephemeral state (Redis) directly into the application container, opting instead to orchestrate them dynamically and rely on robust external managed services in production environments.

## Docker Strategy

### Backend (FastAPI)
- **Base Image**: Lightweight `python:3.11-slim`.
- **System Dependencies**: Includes `libpq-dev` and `gcc` to support `psycopg2` (for PostgreSQL connectivity) and `faiss-cpu`.
- **User Permissions**: Runs securely as a non-root user (`justiassist`).
- **Entrypoint**: `entrypoint.sh` executes the Uvicorn ASGI server.
- **Excluded Assets**: `vector_stores/` and `data/` are explicitly added to `.dockerignore` and mapped via volumes at runtime to prevent image bloat (the FAISS and BM25 indices can be massive).

### Frontend (React/Vite)
- **Multi-stage Build**:
  - *Stage 1 (Node)*: Uses `node:20-alpine` to install dependencies and compile the Vite application into a production-ready static bundle (`npm run build`).
  - *Stage 2 (Nginx)*: Uses `nginx:alpine` to serve the static files and act as a reverse proxy.
- **Nginx Configuration**: Replaces the Vite development proxy. It serves the Single Page Application (SPA) and safely routes all `/api/`, `/query`, `/session/`, and other backend-specific paths directly to the backend container.

## Orchestration (Docker Compose)
A 5-service `docker-compose.yml` provides the local development and demonstration environment.

### Services
1. **`postgres`**: A persistent PostgreSQL 15 database (`postgres:15-alpine`) mapped to a local volume (`postgres_data`). Health is verified via `pg_isready`.
2. **`redis`**: An ephemeral Redis 7 instance (`redis:7-alpine`) used exclusively for caching, aligned with the Phase 7E graceful degradation pattern.
3. **`migrations`**: A transient, one-shot service that uses the backend image to execute `alembic upgrade head`. It depends on `postgres` being completely healthy.
4. **`backend`**: The FastAPI server. Startup relies on `migrations` completing successfully and `postgres` becoming healthy.
5. **`frontend`**: The Nginx container exposing the application on port `3000`.

## Production vs. Local Environments

### Local (Docker Compose)
Compose encapsulates the entire stack. Database and cache are provided locally. Vector indices and local document storage are mapped from the host to ensure persistence across container restarts.

### Production
In a true production environment (e.g., AWS, GCP), the architecture dictates:
- **Backend Containers**: Deployed via ECS, Kubernetes, or Cloud Run, scaling horizontally.
- **Frontend**: Served via a CDN (e.g., CloudFront, Vercel) or a dedicated Nginx ingress.
- **PostgreSQL**: Replaced with a managed relational database (e.g., Amazon RDS, Cloud SQL).
- **Redis**: Replaced with a managed cache (e.g., Amazon ElastiCache, MemoryDB).
- **Object Storage**: Handled by S3 (`STORAGE_PROVIDER=s3`), replacing the local Docker volume.
- **Vector Assets**: Downloaded to a mounted persistent volume (EFS) or baked into a specialized sidecar/init-container depending on scale constraints.

## Health and Resilience
The `/health` endpoint (`api/admin.py`) was overhauled to deeply introspect dependencies:
- **PostgreSQL**: Actively queried (`SELECT 1`). If this fails, the API reports unhealthy.
- **Redis**: Actively pinged. However, because Redis is strictly optional for correctness (Phase 7E), a failure here degrades the cache but **does not** mark the backend as unhealthy.
- **Ollama**: Monitored for fallback capability. 
- **Docker Compose Healthchecks**: Compose uses native `pg_isready`, `redis-cli ping`, and an internal Python-driven HTTP request (to avoid the overhead of `curl` on alpine/slim images) to orchestrate startup sequencing.

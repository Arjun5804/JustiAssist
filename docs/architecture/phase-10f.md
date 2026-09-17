# Phase 10F — Production Deployment Requirements

This document outlines the explicit deployment constraints, preconditions, and known limitations for running JustiAssist v2.0 in a production environment, following the Phase 10F production-readiness hardening.

## 1. Infrastructure Requirements

### Single Backend Worker
**Requirement:** The backend must be deployed as a single Uvicorn/FastAPI process.
**Reason:** The runtime `session_manager` (for uploaded case documents) and the primary FAISS vector indexes are maintained in process-local memory.
**Limitation:** Horizontal scaling (adding multiple backend containers/pods) is **currently unsupported**. If multiple workers handle traffic, a user querying an uploaded document may hit a worker that lacks the document in its local memory, leading to inconsistent behavior. Sticky sessions do not fully mitigate this because FAISS RAM usage scales linearly with each worker process.

### Object Storage Volume (Local)
**Requirement:** If `STORAGE_PROVIDER=local` is used, the configured `LOCAL_STORAGE_ROOT` (default: `.data/storage`) MUST be backed by a persistent disk volume.
**Reason:** The application relies on object storage to persist user document bytes safely. Ephemeral container filesystems will lead to data loss and database/storage inconsistency upon restart.

### Nginx Configuration
**Requirement:** The Nginx reverse proxy must enforce `client_max_body_size 5m;`.
**Reason:** Protects the FastAPI backend from unbounded disk-consumption DoS during temporary file extraction.

### Hardware Resources
**Requirement:** Sufficient RAM for FAISS and sufficient `/tmp` capacity for concurrent document uploads. 
**Reason:** Uploads are written to local `/tmp` files for extraction.

## 2. Environment Preconditions

The application enforces the following strict checks on startup:

* **Environment Variable:** `APP_ENV=production` must be set.
* **Database:** `DATABASE_URL` must point to a PostgreSQL instance. SQLite is explicitly rejected in production to prevent concurrent write locking and data loss.
* **Security:** `JWT_SECRET_KEY` must be a cryptographically secure string of at least 32 characters, overriding the insecure default.
* **Storage Provider Config:** Correctly set for local persistence or S3.

## 3. Index Availability & Startup Lifecycle

* **Indexes Must Be Pre-Built:** The system will not automatically build FAISS vector indexes during startup to avoid expensive initializations in the critical path.
* **Readiness Gate:** The `/health/readiness` probe requires both the `statutory` and `case_law` indexes to be loaded.
* **Admin Build Route:** An administrator must use the `/build-indices` route to trigger index creation if they are missing. The application will safely reject traffic via the load balancer until readiness passes.

## 4. Known Runtime Limitations

* **Session Restart Ephemerality:** While uploaded document bytes and metadata persist safely in PostgreSQL and Object Storage across restarts, **active in-memory document sessions are ephemeral**. 
* **Impact:** A backend process restart will invalidate active `DocumentSession` FAISS states. The user's query context will be lost. Persistent Object Storage does not currently "rehydrate" the in-memory state automatically. This is a deployment/product limitation distinct from horizontal scaling.

## 5. Future Scalability Work (Not Currently Supported)

The following architectural changes are documented as future scalability initiatives and are intentionally excluded from the current baseline:

* **External Vector DB:** Migration from in-memory FAISS to pgvector, Milvus, or Qdrant for stateless retrieval.
* **External Session Manager:** Migration of the `session_manager` to Redis for stateless horizontal scaling and restart rehydration.
* **Distributed Tracing:** OpenTelemetry or Prometheus integration.
* **Kubernetes Orchestration:** Advanced horizontal autoscaling deployments.

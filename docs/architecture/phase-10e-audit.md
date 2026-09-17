# Phase 10E — Observability & Production Health Audit

## Baseline
Repository: `Arjun5804/JustiAssist`
Baseline commit: `7a34b3f9212ad5563f68c6236697460b8f97d7b1`

## Executive Summary
The audit of JustiAssist's current observability architecture reveals an ad-hoc system that is functional for development but lacks the rigor needed for production. While unstructured plaintext logs exist and a custom in-memory metrics collector tracks basic statistics, the system critically lacks request correlation, making it extremely difficult to trace a single user query through the HTTP, orchestrator, retrieval, generation, and SSE pipeline. Additionally, the structured audit logger currently captures full user queries, posing a significant PII and privacy risk. The Phase 10E implementation should focus on lightweight, high-value improvements: request correlation, log structuring, PII masking, and distinct health endpoints, while deferring heavy instrumentation like OpenTelemetry to a later phase.

## Current Observability Architecture
- **Logging:** Standard Python `logging` module.
- **Metrics:** Custom thread-safe `MetricsCollector` in `metrics.py`.
- **Audit Logging:** Structured JSONL logger in `audit_logger.py`.
- **Endpoints:** `/health`, `/metrics`, and `/stats` exposed via FastAPI in `api/admin.py`.

## Logging Audit
- **Framework:** Standard `logging` module is used across components (`logger = logging.getLogger(__name__)`).
- **Structured vs Text:** Application logs are unstructured plaintext. Audit logs are structured JSONL.
- **Log Levels:** Used loosely. `exc_info=True` is correctly used in `core/errors.py` to expose stack traces in backend logs without leaking them to users.
- **Secrets & PII:** `audit_logger.py` records full `query_text` and `reformulated_query`. This is a critical privacy risk as it may capture PII or confidential legal case facts. Secrets (API keys, JWTs) are correctly excluded from logs.
- **Security Events:** Rate limit violations log warnings. Authentication failures are logged. However, there is no distinct security event classification.
- **Startup Logging:** Relies on unstructured `print()` statements in `app.py`'s `lifespan`.

## Request / Correlation Observability
- **Request IDs:** Do not exist.
- **Correlation:** Missing across the pipeline (HTTP request → AgentOrchestrator → RetrievalPipeline → LLM → SSE response). It is currently impossible to definitively correlate an error in the LLM provider back to the specific SSE stream or user request that triggered it.
- **Smallest fix:** Implement a lightweight ASGI middleware to generate a unique `request_id` (or `correlation_id`) and inject it into all log records using Python's `contextvars`.

## AI / RAG Observability
- **Tracked:** Total queries, hit rate, average retrieval score, grounding rate, citation validity, and latency (`metrics.py`).
- **Missing in Metrics:** The exact breakdown of retrieved statutory vs. case-law results, external results count, reranker rejection rates, and explicit verification failure counts are tracked in state (e.g., `VerificationSummary`) but are not aggregated or exposed in `/metrics`.

## Health & Readiness
- **Endpoints:** A single `/health` endpoint exists in `api/admin.py`.
- **Checks:** Validates Database (SELECT 1), Redis (Ping), Ollama (/api/tags), and VectorStore initialization status.
- **Liveness vs Readiness:** There is no distinction. The single endpoint sets `status = "healthy" if db_status == "connected" else "unhealthy"`.
- **Dependency Nuance:** It correctly fails open if Redis is down (Redis is optional for correctness). However, it does not check Groq (the primary LLM) or external providers (Firecrawl/Kanoon). 

## Dependency Health
- **Postgres:** Explicitly checked.
- **Redis:** Explicitly checked.
- **LLM Providers:** `LLMProvider` retries and falls back seamlessly, but their ongoing health isn't continuously monitored outside of active requests.
- **External Retrieval:** `hybrid_retriever.py` correctly implements the 10D timeouts (Kanoon=3s, News=2s). Firecrawl relies on the default SDK timeout.

## SSE Observability
- **Implementation:** `api/query.py` uses an `asyncio.Queue` and a background task for the SSE stream.
- **Visibility:** Client disconnects (`asyncio.CancelledError`) and backend errors are caught and logged. However, there are no metrics tracking the number of active SSE connections or their duration.
- **Error Handling:** Backend correctly sends a generic error (`{"type": "error", "message": "..."}`) to the client while preserving full stack traces internally.

## Startup / Shutdown
- **Startup:** If the Vector store is missing, `app.py` prints a warning but allows the application to start. This could lead to a degraded production state that isn't immediately obvious to orchestration tools.
- **Shutdown:** No explicit graceful shutdown handling beyond FastAPI's default process termination.

## Metrics & Tracing
- **Existing:** Custom `metrics.py` exposed via `/metrics`.
- **Tracing:** No OpenTelemetry or tracing frameworks exist.
- **Evaluation:** For a portfolio project hardening towards production, introducing a full Prometheus/OpenTelemetry stack in Phase 10E is overkill and should be deferred.

## Security / Privacy Considerations
- **PII Risk:** As noted, `audit_logger.py` logs full user queries.
- **What SHOULD NOT be logged:** User prompts, uploaded document contents, legal case facts, authentication tokens, SSE tickets, API keys, email addresses, and IP addresses (unless specifically required for rate-limiting audit).

## Resource & Scaling Visibility
- Memory growth, FAISS vector store memory footprint, DB connection pool pressure, and concurrent SSE/AI requests are currently untracked, making it difficult to detect resource exhaustion.

## Docker / Deployment Observability
- `docker-compose.yml` includes health checks for `postgres` and `redis`.
- The `backend` container's health check hits the unified `/health` endpoint using `urllib`.

## Test Coverage
- Minimal. There is likely insufficient test coverage specifically asserting logging behavior, correlation ID propagation, or metric accuracy.

---

## Findings by Severity

### P0 — Production Blocker
None strictly blocking immediate execution, but PII logging is a critical compliance risk.

### P1 — High Priority
- **File:** `audit_logger.py`
  - **Current Behavior:** Logs full `query_text` which may contain PII or sensitive case facts.
  - **Recommended Fix:** Hash or redact full query text from production audit logs.
  - **Phase:** 10E
- **File:** `api/admin.py`
  - **Current Behavior:** Single `/health` endpoint merges Liveness and Readiness.
  - **Recommended Fix:** Split into `/health/liveness` (returns 200 if API is responsive) and `/health/readiness` (returns 200 only if DB and VectorStore are ready).
  - **Phase:** 10E
- **File:** `app.py` / `core/logger.py`
  - **Current Behavior:** Missing request correlation IDs.
  - **Recommended Fix:** Implement a lightweight `request_id` middleware and a `ContextVar` logger adapter.
  - **Phase:** 10E
- **File:** `api/admin.py`
  - **Current Behavior:** `/metrics` and `/stats` are accessible by any authenticated user.
  - **Recommended Fix:** Restrict these endpoints to an admin role or internal network only.
  - **Phase:** 10E

### P2 — Medium Priority
- **File:** `metrics.py`
  - **Current Behavior:** Missing detailed AI/RAG metrics (e.g., statutory vs case-law breakdown, SSE connection counts).
  - **Recommended Fix:** Enhance `metrics.py` to aggregate these specific signals.
  - **Phase:** 10E
- **File:** `app.py`
  - **Current Behavior:** Plaintext application logs.
  - **Recommended Fix:** Implement a JSON formatter for application logs in production.
  - **Phase:** 10E

### P3 — Future
- OpenTelemetry distributed tracing.
- Prometheus `/metrics` exporter.
- Deep FAISS memory profiling.

---

## Recommended Phase 10E Scope
1. Implement request correlation ID middleware using `contextvars`.
2. Configure JSON logging for application logs (excluding development mode).
3. Split the unified health endpoint into distinct `/health/liveness` and `/health/readiness` endpoints.
4. Enhance `metrics.py` to track specific RAG signals (statutory vs case-law counts) and active SSE connection counts.
5. Redact or remove PII (`query_text`) from `audit_logger.py`.
6. Restrict admin observability endpoints (`/metrics`, `/stats`) to authorized users.

## Explicitly Out-of-Scope (Deferred Work)
- OpenTelemetry integration.
- Prometheus exporters.
- Adding new logging to the frontend.
- Refactoring the FAISS in-memory architecture to out-of-process stores.

## Acceptance Criteria for Phase 10E Implementation
- All application log entries include a unique `request_id`.
- Application logs are JSON-formatted in the production environment.
- `/health/liveness` returns 200 independently of backend database status.
- `/health/readiness` correctly validates required dependencies.
- PII and full user queries are no longer stored in `audit_logger.py`.

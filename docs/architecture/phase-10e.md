# Phase 10E — Observability & Production Health

## Observability Architecture

```text
                 HTTP Request
                      │
                      ▼
          Request Correlation Middleware
                      │
              ┌───────┴───────┐
              ▼               ▼
         JSON Logging      X-Request-ID
              │
              ▼
        Existing Agent Pipeline
              │
              ▼
       Validated Evidence
              │
              ├──────────────► RAG Metrics
              │
              ▼
          Grounded Generation
              │
              ▼
       Claim Verification
              │
              ├──────────────► Verification Metrics
              │
              ▼
          Final Answer
              
        SSE lifecycle
              │
              ├── active +1
              └── finally → active -1
```

## Request ID Behavior
- `X-Request-ID` is assigned via the `RequestCorrelationMiddleware`. 
- An incoming `X-Request-ID` header is conservatively validated (alphanumeric, <64 chars) and preserved. Otherwise, a UUID4 is generated.
- The ID is stored in a Python `contextvar` (`correlation_id_var`) and exposed to the standard logging module.
- `finally` ensures the `ContextVar` is reset so it cannot leak across asynchronous tasks.

## Log Format & Privacy Rules
- **Production Logs:** Formatted as single-line JSON via `JSONLogFormatter`. Includes `request_id`, `logger`, `level`, `timestamp`, and `message`.
- **Development Logs:** Formatted as standard human-readable text logs but injected with `[req:id]`.
- **Privacy:** `audit_logger.py` uses deterministic SHA-256 to hash `query_text` and `reformulated_query` before persistence. Raw query facts (potentially PII) are explicitly *not* serialized to the persistent audit log. Sensitive context (JWTs, Passwords) are excluded.

## Health Semantics
- `/health/liveness`: Fast and dependency-free. Returns HTTP 200 `{"status": "alive"}` indicating the application process is running and accepting connections.
- `/health/readiness`: Assesses core functional capabilities. Returns HTTP 200 when Postgres is available and required VectorStore indexes are loaded. Returns HTTP 503 `{"status": "not_ready"}` otherwise.

## Readiness Dependencies
- **PostgreSQL:** REQUIRED for `/health/readiness`
- **VectorStore:** REQUIRED for `/health/readiness`
- **Redis:** OPTIONAL. Reported but does not cause readiness failure.
- **External Providers (Groq/Ollama, Firecrawl, Kanoon, GNews):** OPTIONAL. Not checked during readiness to prevent cascading failures if third-party endpoints go down.

## Metrics Semantics
- `statutory_results_total`: Number of validated statutory evidence chunks observed in the pipeline.
- `case_law_results_total`: Number of validated case-law chunks observed.
- `external_results_total`: Number of validated external (Firecrawl/Kanoon) chunks observed.
- `session_document_results_total`: Number of validated chunks originating from user uploaded session documents.
- `verifications_supported`: Number of generated claims receiving a `SUPPORTED` verdict from the Verification Agent.
- `verifications_rejected`: Number of generated claims receiving any non-supported verdict.
- `answers_abstained`: Number of final responses where the entire Agent State is marked as abstained.

## SSE Metrics
- `sse_active_connections`: Concurrent gauge incremented when an SSE starts, and decremented safely inside a `finally` block when the stream finishes (normal completion, error, or client disconnect).
- `sse_completed_total`: Monotonic counter of completed streams.
- `sse_errors_total`: Monotonic counter of stream errors/exceptions.

## Admin Endpoint Authorization
- Access to `/metrics`, `/stats`, and `/build-indices` requires authorization.
- An authenticated user's email is checked against the comma-separated `ADMIN_EMAILS` environment variable.
- Defaults to fail-closed (`403 Forbidden`) if no admin emails are configured or the user's email is not present in the list.

## Explicitly Deferred / Out of Scope
- OpenTelemetry tracing.
- Prometheus exporters.
- Frontend observability.
- Replacing standard `logging` with another framework.
- Replacing in-memory FAISS architecture.
- Database schema migrations for Role models.

## Phase 10D Timeouts preserved
- Firecrawl: 10s
- GNews: 10s
- Indian Kanoon: 3s

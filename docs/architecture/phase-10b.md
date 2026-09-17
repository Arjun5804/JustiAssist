# Phase 10B — Security & Secrets Hardening

## Overview
Phase 10B focuses on securing the JustiAssist production environment against token leakage and unhandled exceptions, without altering the core Retrieval-Augmented Generation (RAG) architecture.

## Implementation Details

### 1. SSE Ticket Architecture
- **Problem**: The SSE endpoint previously accepted the long-lived access JWT in the query string (`?token=...`), which exposed it to proxy logs and history.
- **Solution**: Implemented a short-lived ticket system.
  - New Endpoint: `POST /api/auth/sse-ticket` protected by standard Bearer authentication.
  - The endpoint issues a 30-second TTL signed JWT with a specific `type="sse"` claim.
  - The frontend now fetches this ticket asynchronously and appends it to the SSE URL (`?ticket=...`).
  - The backend `decode_sse_ticket` function rejects ordinary access JWTs, expired tickets, and missing tickets.
- **Replay Prevention**: Deferred to Phase 10C/10D. For now, the short 30-second TTL and unique `jti` minimize exposure compared to long-lived tokens.
- **Ticket Claims**:
  - `sub`: Authenticated user ID (binds the ticket to the user's session).
  - `type`: "sse" (prevents access token reuse).
  - `exp`: Current time + 30 seconds.
  - `jti`: Unique ticket identifier.
  - `iat`: Issued at time.

### 2. Global Exception Sanitization
- **Problem**: Raw exceptions (e.g., SQLAlchemy tracebacks) were previously returned to clients in HTTP 500 errors.
- **Solution**: Added global exception handlers in `core/errors.py`.
  - All unhandled `Exception`s and `StarletteHTTPException`s with status code >= 500 are caught.
  - The full exception and traceback are logged server-side.
  - The client receives a generic response: `"An internal error occurred while processing your request."`
  - Expected HTTP errors (400, 401, 403, 404, 422) retain their intentional client-facing details.

### 3. SSE Error Sanitization
- Streaming errors in `api/query.py` now yield the same generic safe error message.
- The actual exception is logged server-side (`logger.error`).

### 4. Production Configuration Fail-Closed
- **Problem**: The production environment could inadvertently use SQLite or development defaults.
- **Solution**: Updated `config.py` `validate_production_security`.
  - Rejects `DATABASE_URL` starting with `sqlite` or `sqlite+aiosqlite` when `APP_ENV=production`.
  - Enforces the use of PostgreSQL in production environments.
  - Retains SQLite support for development and testing.

### 5. Nginx SSE Configuration
- Added a specific regex location block (`location ~ ^/api/(v2/)?query/stream`) to `frontend/nginx.conf`.
- Disabled buffering and caching (`proxy_buffering off;`, `proxy_cache off;`).
- Configured a 300s read timeout (`proxy_read_timeout 300s;`).
- This ensures SSE streams remain open and responsive without applying aggressive settings to standard API routes.

## Tests Added
- **Configuration**: Verifies production rejects SQLite and weak secrets.
- **SSE Ticket**: Validates ticket expiration, incorrect types, ordinary access token rejection, and user mapping.
- **Authorization**: Ensures a valid SSE ticket for User A cannot access User B's conversation.
- **Exception Handling**: Confirms internal exceptions return generic responses and do not expose original messages.

## Deferred Work
- Distributed replay prevention for SSE tickets.
- Rate limiting, login/signup throttling (Redis).
- Session migration to Redis.
- FAISS distributed storage.
- Horizontal worker redesign.
These remain planned for Phase 10C/10D. Production readiness is not declared yet.

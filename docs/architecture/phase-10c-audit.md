# Phase 10C API / Auth / Rate-Limit Hardening Audit

## 1. Executive Summary

This document presents a focused production-security audit of the JustiAssist API, Authentication, and Abuse-Control architecture based on the Phase 10B baseline. The audit reveals critical vulnerabilities, particularly in input validation, unauthenticated expensive endpoints, unauthenticated admin operations, and a complete lack of rate limiting across all operations. This audit establishes the minimal implementation scope for Phase 10C.

## 2. Current Authentication Architecture

- **Signup (`/api/auth/signup`)**: No authentication required. Performs DB write and bcrypt hashing. No rate limits. Returns `Email already registered`, allowing email enumeration.
- **Login (`/api/auth/login`)**: No authentication required. Validates password. No rate limits or brute-force protections. A timing attack is possible because bcrypt is only executed if the user exists, allowing account enumeration.
- **Current User (`/api/auth/me`)**: JWT Bearer token authentication required. No specific abuse protections beyond standard API limits.
- **SSE Ticket (`/api/auth/sse-ticket`)**: JWT Bearer required. Issues short-lived (30s) JWT for SSE streams. No rate limit on issuance, allowing token flooding.
- **Token Infrastructure**: Stateless JWTs with a configured expiry (`JWT_EXPIRY_HOURS`). No refresh mechanisms and no revocation capabilities.
- **Password Hashing**: Uses `bcrypt` with 12 rounds. It is executed synchronously, which can block the asyncio event loop under high load.

## 3. API Abuse-Surface Inventory

| Endpoint | Auth | Cost | Abuse Risk | Current Limit | Recommended Limit Class | Priority |
| -------- | ---- | ---- | ---------- | ------------- | ----------------------- | -------- |
| `/api/auth/signup` | None | DB/CPU (Bcrypt) | Bot registration, Email enum | None | Strict IP | P0 |
| `/api/auth/login` | None | DB/CPU (Bcrypt) | Credential stuffing, Enum | None | Strict IP / Account | P0 |
| `/api/auth/sse-ticket` | JWT | CPU | Token flooding | None | Moderate User | P1 |
| `/api/v2/query` | Optional | High (LLM/DB) | Resource exhaustion | None | Strict IP / User | P0 |
| `/api/v2/query/stream` | Ticket | High (LLM/DB) | Resource exhaustion | None | Strict IP / User | P0 |
| `/upload-document` | JWT | High (Storage/CPU)| DoS via large files | 5MB size | Moderate User | P1 |
| `/api/predict/case` | None | High (LLM) | Resource exhaustion | None | Strict IP | P0 |
| `/api/documents/generate`| None | High (LLM) | Resource exhaustion | None | Strict IP | P0 |
| `/api/counter-arguments` | None | High (LLM) | Resource exhaustion | None | Strict IP | P0 |
| `/api/sandbox/quiz` | None | High (LLM) | Resource exhaustion | None | Strict IP | P1 |
| `/api/sandbox/moot-court`| None | High (LLM) | Resource exhaustion | None | Strict IP | P1 |
| `/build-indices` | None | High (DB/FAISS) | Rebuild DoS / Admin exploit | None | Strict Admin | P0 |

## 4. Rate-Limit / Redis Audit

Phase 7E introduced a lightweight `CacheService` in `services/cache.py`.
- **Initialization**: Uses `redis.asyncio.from_url` with lazy connection.
- **Failure Handling**: Gracefully degrades to a no-op / cache miss without crashing the app.
- **Current Methods**: Exposes `get`, `set` (with TTL), and `delete`.
- **Atomicity**: Currently lacks atomic `INCR` or Lua script execution required for robust rate limiting.
- **Recommendation**: Rate limiting should be **Redis-backed**, **fail-open** (allow requests if Redis is down to preserve availability), and **endpoint-dependent**. We should extend the existing `CacheService` (or create a sibling service using the same Redis pool) with atomic increment operations rather than creating a second Redis connection abstraction.

## 5. Client Identity / Proxy Audit

- **Nginx Config**: `frontend/nginx.conf` sets `X-Real-IP` and `X-Forwarded-For` when proxying to the backend.
- **FastAPI Handlers**: Currently, FastAPI does not explicitly read `X-Real-IP`.
- **Spoofing Risk**: If the application directly binds to a public port and trusts proxy headers, IPs can be spoofed. However, in the Docker setup, the backend is internal.
- **Safest Minimal Approach**: Read the `X-Real-IP` header set by Nginx, falling back to `request.client.host` if the header is absent.

## 6. Input and Resource Limit Audit

- **P0: Unbounded Text Fields**: Pydantic models in `api/features.py` (`CasePredictionRequest`, `CounterArgumentRequest`, `MootCourtRequest`) lack a `max_length` constraint for fields like `case_facts`, `legal_argument`, `case_scenario`, and `user_argument`. This allows a malicious client to send multi-megabyte payloads, exhausting memory and LLM context limits.
- **P1: Unbounded Dict/Array Limits**: `DocumentGenerationRequest` accepts an unbounded dictionary for `form_data`. `QueryRequest` has unbounded list lengths for `offense_sections`.
- **P1: Document Limits**: Upload limits file size to 5MB, but there is no limit on the number of documents uploaded per session.

## 7. Authentication Abuse Analysis

- **Login Timing Attack**: The `verify_password` function is conditionally skipped if the user does not exist in the database. This timing difference allows attackers to enumerate registered emails.
- **Ticket Replay**: SSE tickets contain a `jti` claim, but the backend does not track used `jti`s. A ticket can be reused repeatedly within its 30-second validity window.
- **Credential Stuffing**: There are no rate limits on the login endpoint to prevent credential stuffing.
- **Token Expiration**: Access tokens are stateless and expire after `JWT_EXPIRY_HOURS`. Refresh tokens and token revocation are not implemented.

## 8. Expensive AI / RAG Endpoint Analysis

- **Query / SSE Stream**: Execution triggers FAISS, BM25, Reranking, and LLM inference.
- **Features (`/api/predict/case`, etc.)**: Execution triggers FAISS and LLM inference. Currently entirely unauthenticated.
- **Document Upload**: Triggers PDF/DOCX parsing, chunking, and FAISS indexing.
- **Conclusion**: These expensive endpoints must be heavily rate-limited independent of standard API limits. Unauthenticated RAG endpoints must be secured or tightly throttled.

## 9. Admin Endpoint Analysis

- **Vulnerability**: Admin endpoints such as `/build-indices`, `/stats`, and `/api/news` in `api/admin.py` have **no authentication or authorization dependencies**.
- **Impact**: Any user can trigger index rebuilding, which locks the FAISS index and causes high CPU/DB load. This is a severe P0 vulnerability.

## 10. Existing Test Coverage

Current tests cover basic authentication and Phase 10B security enhancements (`test_security_10b.py`). Phase 10C will require a new test matrix:
- Normal requests under limit
- Requests exceeding limit (429 Too Many Requests, Retry-After header)
- Rate limit isolation across independent users and IPs
- Fail-open behavior when Redis is unavailable
- Login brute force and signup abuse scenarios
- Admin endpoints enforcing proper authentication

## 11. Findings by Priority

- **P0**: Admin operations (`/build-indices`) lack authentication. *Action: Add `Depends(get_current_user)` (and ideally an admin role check) to admin routes.*
- **P0**: Unbounded input fields in AI feature models (`case_facts`, `legal_argument`). *Action: Add strict `max_length` to Pydantic models.*
- **P0**: No rate limit on Login/Signup. *Action: Implement strict rate limiting.*
- **P0**: No rate limit on expensive AI RAG routes. *Action: Implement strict LLM-tier rate limiting.*
- **P1**: Login timing attack allowing email enumeration. *Action: Execute dummy bcrypt hash when user is not found.*
- **P1**: SSE ticket flooding. *Action: Implement rate limit on ticket issuance.*
- **P2**: Unbounded list parameters in `QueryRequest`. *Action: Add `max_items` to Pydantic definitions.*
- **P3**: SSE ticket replay within 30s. *Defer tracking `jti` to avoid statefulness for now.*

## 12. Proposed Minimal Phase 10C Scope

**Must fix in Phase 10C:**
1. Secure admin endpoints with authentication.
2. Apply `max_length` constraints to all Pydantic models (specifically in `features.py` and `query.py`).
3. Mitigate login timing attack by performing a dummy hash calculation.
4. Implement a Redis-backed, fail-open rate limiting abstraction.
5. Apply specific rate-limit categories (e.g., Auth, LLM, Standard) to critical endpoints using `X-Real-IP` and User ID.

**Defer to Phase 10D:**
- Token revocation and refresh token architecture.
- Advanced account lockout mechanisms.

**Defer to Phase 10E:**
- Observability and metrics for rate-limited requests.

**Defer beyond Phase 10:**
- Complex abuse tracking (e.g., CAPTCHA integration).

## 13. Proposed Rate-Limit Architecture

- **Service**: Implement `RateLimitService` reusing the `redis.asyncio` connection from `CacheService`.
- **Atomicity**: Use an atomic pipeline or Lua script to perform `INCR` and `EXPIRE` simultaneously to prevent race conditions.
- **Identity Dimensions**:
  - Unauthenticated requests: rate-limit by `X-Real-IP`.
  - Authenticated requests: rate-limit by `User ID`.
  - Endpoint Category: `auth`, `llm`, `standard`, `sse_ticket`.
- **Behavior**: Return HTTP `429 Too Many Requests` with a `Retry-After` header when limits are exceeded.
- **Fail-Open**: If the Redis client raises an exception (e.g., connection refused), the rate-limiter should catch the error, log a warning, and allow the request to proceed.

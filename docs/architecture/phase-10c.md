# Phase 10C: API / Auth / Rate-Limit Hardening

## Overview
Phase 10C focuses on hardening JustiAssist's API endpoints against abuse, bounding resource consumption, and mitigating authentication attacks.

## Implementation Details

### 1. Centralized Rate Limiting
- **Location:** `core/rate_limit.py`
- **Mechanism:** Redis Lua script for atomic `INCR` + `EXPIRE`. The threshold correctly ensures the exact Nth request is allowed and the (N+1)th request is rejected. Redis `NOSCRIPT` cache loss is dynamically caught and retried, and fail-open behavior is preserved if Redis is unavailable. `Retry-After` header accurately rounds up TTL to ensure it is never zero while actively blocked.
- **Dependency:** `RateLimiter` class implemented as a FastAPI dependency, with strict configuration parsing.
- **Identity Extraction:** Authenticated `user.id` or fallback to `X-Real-IP` (Nginx) / client host.
- **Categories:**
  - `AUTH`: 5/minute (Signup, Login)
  - `LLM`: 10/minute (Query, Sandbox features)
  - `SSE_TICKET`: 20/minute
  - `UPLOAD`: 5/minute

### 2. Privilege Separation
- **Location:** `api/admin.py`
- **Mitigation:** Applied `Depends(get_current_user)` to `/build-indices`, `/stats`, and `/api/news` to restrict access to authenticated users.

### 3. Resource Bounds
- **Location:** `api/features.py`, `api/query.py`
- **Mitigation:** Applied bounded Pydantic constraints:
  - `max_length=5000` for `case_facts`, `legal_argument`, `case_scenario`
  - `max_length=3000` for `user_argument`
  - `max_length=10` (or 20) for lists like `sections_involved`, `offense_sections`

### 4. Authentication Hardening
- **Location:** `services/auth.py`
- **Mitigation:** Protected against login timing enumeration by executing `verify_password` against a pre-computed valid dummy bcrypt hash (`DUMMY_PASSWORD_HASH`) when an email is not found.

## Testing
- Security regression tests implemented in `tests/api/test_security_10c.py` using `unittest.mock.patch` to verify rate-limiter invocation and authentication behavior without relying on a live Redis instance during testing.

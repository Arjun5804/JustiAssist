# Phase 7E: Redis / Caching Architecture

## Overview
Phase 7E introduces Redis as an optional, application-level cache to reduce repeated database and read-path work while strictly preserving PostgreSQL/SQLite and existing state as the single source of truth.

## Cache-Aside Flow
The caching layer implements a lock-free cache-aside pattern:
1. **Read Path**: The application attempts to fetch a key from the cache.
   - **Hit**: The cached value is deserialized and returned.
   - **Miss**: The application executes the primary database query, serializes the result, populates the cache with an explicit TTL, and returns the result.
2. **Write Path**: Database writes (inserts, updates, deletes) are committed first. After a successful database commit, the relevant cache keys are explicitly deleted (invalidated).

## Graceful Degradation
Redis is treated strictly as an optimization, not a correctness dependency.
- If Redis is unavailable during startup, `CacheService` degrades gracefully and logs a warning.
- If any cache GET/SET/DELETE operation fails at runtime (e.g., connection lost, malformed JSON), the error is caught, logged as a warning, and the application degrades to the primary database path without propagating exceptions to the user.
- Cache invalidation failures do *not* roll back the successful primary database transaction.

## Cached Candidates

### 1. Chat History
- **Key**: `justiassist:v1:chat:history:{user_id}:{conversation_id}`
- **TTL**: 3600 seconds (1 hour)
- **Serialization**: `List[Dict[str, Any]]` containing full message representations.
- **Invalidation**: Cleared upon new message save (`save_message`) or history deletion (`clear_history`).

### 2. Recent Conversations
- **Key**: `justiassist:v1:chat:conversations:{user_id}`
- **TTL**: 900 seconds (15 minutes)
- **Serialization**: `List[Dict[str, Any]]` summarizing conversations.
- **Invalidation**: Cleared upon new message save (`save_message`) or history deletion (`clear_history`).

### 3. Session Documents List
- **Key**: `justiassist:v1:docs:session:{user_id}:{session_id}`
- **TTL**: 1800 seconds (30 minutes)
- **Serialization**: `List[Dict[str, Any]]` containing document metadata.
- **Invalidation**: Cleared upon document upload, deletion, or session clearing.

## Explicitly Excluded Candidates (Rejected)
To maintain the integrity of legal answering and ensure deterministic evaluation:
- LLM responses and legal conclusions
- FAISS/BM25 retrieval results
- Evidence validation and claim verification outputs
- External web search results
- Document bytes (object storage remains authoritative)
- Authentication tokens

## Configuration
- `REDIS_ENABLED` (default: `False`): Must be explicitly set to `True` to activate caching.
- `REDIS_URL` (default: `redis://localhost:6379`)
- `REDIS_DEFAULT_TTL` (default: `3600` seconds)

## Key Versioning & Serialization
All keys include a `v1` namespace (e.g., `justiassist:v1:...`). If the serialized dictionary structure for any cached object changes in the future, this version number must be incremented to prevent deserialization errors from stale cache entries.

## Testing Strategy
- Tests utilize mocking to verify graceful degradation paths without requiring a live Redis server.
- Tests validate user-isolation in key generation.
- Tests confirm that simulated JSON decode errors or connection errors gracefully fall back to database queries.
- The default test suite can be run with `REDIS_ENABLED=false` or mocked cache responses.

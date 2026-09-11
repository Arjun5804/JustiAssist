# Phase 0B — Safe Modularization

## Objective
Extract route handlers from the 2,547-line `app.py` monolith into a modular `api/` package while preserving exactly the same runtime behavior, dependencies, and test outcomes.

## What Moved
1. **API Routes**: Extracted 22 route handlers from `app.py` into focused modules:
   - `api/auth.py` (Signup, Login, User info)
   - `api/chat.py` (Chat history CRUD)
   - `api/query.py` (v2 query pipeline, streaming, and legacy query endpoints)
   - `api/documents.py` (Session document uploads and queries)
   - `api/features.py` (Case prediction, counter arguments, sandbox, generation)
   - `api/kanoon.py` (Indian Kanoon search API)
   - `api/admin.py` (Health, metrics, stats, news, and index builder)

2. **Global Dependencies**: 
   - Moved the scattered global variables from `app.py` (e.g. `vector_store`, `crew_orchestrator`, `llm_provider`) into a centralized `DepsContainer` class in a new `core/dependencies.py` module.
   - `app.py` initializes the fields on `deps` during the `lifespan` event.
   - All `api/*.py` modules access these singletons via `deps.vector_store`, etc.

## What Intentionally Did NOT Change
- **No pipeline redesign**: The legacy `/query` endpoints and v2 `/api/v2/query` endpoints were copied exactly as they were. Duplicate logic remains intact.
- **No functional refactoring**: Agents, reranking, prompts, confidence scoring, and retrieval logic are 100% untouched.
- **No new frameworks**: CrewAI (despite Python 3.14 incompatibility), SQLite, and in-memory caches remain exactly as they were.
- **Test suite**: No modifications were made to the tests. Pre-refactoring failures due to `pytest-asyncio` misconfiguration continue to fail in the exact same way, while `test_section_boost.py` continues to pass.

## Result
- `app.py` has been reduced from 2,547 lines to ~220 lines.
- It acts strictly as a composition root: running the lifespan, configuring FastAPI middleware, and registering the `api/` routers.
- The application starts cleanly and passes the verification criterion: zero new regressions.

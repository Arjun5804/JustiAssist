# Phase 9: CI/CD + Automated Quality Gates

## Overview
Phase 9 introduces a reliable GitHub Actions CI pipeline that automatically validates the backend and frontend on repository changes. The primary goal is automated enforcement of quality gates through standardized, reproducible checks across backend tests, frontend builds, and database migrations.

## Workflow Triggers
The workflow runs automatically on:
- `push` to the `main` branch
- `pull_request` targeting any branch

## Jobs and Checks

### Backend Validation
- **Python Version**: 3.11 (matched with `Dockerfile` for production parity)
- **Dependency Installation**: `pip install -r requirements.txt` (utilizes pip caching)
- **Compile Check**: `python -m compileall -q .` (validates syntax and import compilation)
- **Tests**: `python -m pytest`

### Migration Validation
- Isolated job checking database migration consistency.
- **Alembic Check**: `alembic check` ensures that no SQLAlchemy model changes exist without corresponding Alembic migrations.

### Frontend Validation
- **Node Version**: 20.x (LTS, compatible with the Vite + React 19 stack)
- **Dependency Installation**: `npm ci` (deterministic installation, utilizes npm caching)
- **Build**: `npm run build` (validates that the production frontend bundle compiles)
- **Lint**: `npm run lint` (runs ESLint on the frontend)

## Test Environment & External Service Isolation
The test environment runs with specific environment variables designed to bypass external service dependencies and production credentials:
- `APP_ENV=testing`
- `JWT_SECRET_KEY` set to a safe dummy value.
- `DATABASE_URL` set to `sqlite+aiosqlite:///./test_ci.db`.

**External Services Excluded**:
- No live network calls to Groq API, Firecrawl API, or Indian Kanoon. Tests rely on the mocked retrieval setup established in Phase 5.
- Redis and Ollama are excluded.
- Production PostgreSQL is omitted; SQLite is used to run migration validation and tests deterministically.

## Limitations and What CI Does NOT Do
- This CI is strictly for **Quality Gates**.
- It does **NOT** deploy to any environment (Kubernetes, AWS/GCP, Terraform, etc.).
- It does **NOT** build or publish Docker images to a registry.
- It does **NOT** modify the repository automatically or fix existing lint errors. Any lint errors currently present in the codebase will surface as legitimate CI blockers that require a separate targeted repair.

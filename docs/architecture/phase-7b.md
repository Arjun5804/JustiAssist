# Phase 7B: Database Modernization & Migration Architecture

## Overview
JustiAssist has transitioned its database layer from implicit schema creation (`Base.metadata.create_all()`) to explicit, versioned schema management utilizing Alembic. This transition separates the operational lifecycle of the database from the application's startup behavior, increasing safety in production deployments.

## Supported Database Backends
1. **SQLite (`sqlite:///*`)**: Maintained as the default configuration for local development and testing to preserve an agile feedback loop without requiring a containerized environment.
2. **PostgreSQL (`postgresql:///*`)**: Supported natively for staging and production deployments. The `psycopg2-binary` driver handles the synchronous engine requirements.

## Alembic Responsibility
Alembic acts as the sole mechanism for creating and updating the database schema in production. The configuration dynamically targets the application settings (`settings.DATABASE_URL`) without duplicating sensitive credentials inside `alembic.ini`.

### Migration Workflow
* **Autogeneration:** Migrations can be generated using `alembic revision --autogenerate -m "message"`. 
* **Manual Review:** Alembic autogeneration is treated as a *candidate* migration. All schema output must be verified to prevent accidental deletions or incorrect index creations before being committed to version control.
* **Operational Commands:**
  * To upgrade to the latest schema: `alembic upgrade head`
  * To roll back the last migration step: `alembic downgrade -1`
  * To roll back to empty state: `alembic downgrade base`

## Why `create_all()` is No Longer Production Schema Management
In previous architectures, the FastAPI `lifespan` hook invoked `create_all()` implicitly on startup. 
While functional for initial MVPs, this pattern:
- Causes race conditions if multiple application instances start concurrently.
- Fails to reflect dropped columns, constraints, or index modifications.
- Obscures database mutation state from infrastructure-as-code deployments.

The implicit `init_db()` lifecycle event has been removed. The application now assumes the connected database has been externally managed via Alembic prior to execution.

## Testing Architecture
Tests run against SQLite and have isolated schema generation located in `tests/conftest.py` using `autouse=True`. This permits headless CI testing to seamlessly create testing tables on the fly without running Alembic commands, protecting application startup code from test-specific side effects.

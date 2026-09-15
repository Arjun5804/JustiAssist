# Phase 7A: Configuration & Environment Hardening

## Overview
Phase 7A transitions JustiAssist from decentralized `os.getenv` configuration to a unified, statically typed, environment-driven configuration model using `pydantic-settings`. This hardens the foundation before introducing advanced infrastructure (PostgreSQL, Redis, Docker) in Phase 7B.

## Key Changes

### 1. Authoritative Settings Model
- Replaced inline `os.getenv` and `load_dotenv()` with a centralized `Settings` class in `config.py`.
- Exposed a single `settings` object that handles all environment defaults and overrides.
- Implemented environment-specific validation via `APP_ENV`. For instance, running with `APP_ENV=production` explicitly rejects missing or weak `JWT_SECRET_KEY`s.

### 2. Dependency Cleanup
- Removed stale legacy `CrewAI` (`crewai`, `crewai-tools`) dependencies from `requirements.txt`.
- Removed stale legacy `CrewAI` references in startup scripts and documentation.
- Added `pydantic-settings` to manage configuration securely.

### 3. Environment Awareness
- Clearly delineated `development` from `production` environments via the `APP_ENV` variable.
- Updated CORS setup (`ALLOWED_ORIGINS`) to be dynamically read from `settings`.

### 4. LLM Providers
- Clarified that **Groq** is the primary intended provider for the application, enforcing explicit API key variables in the `.env.example`.
- Retained **Ollama** as an optional fallback provider but removed any implicit requirement for it to be active during app startup.

### 5. Secrets Management
- Sensitive configurations (e.g., `JWT_SECRET_KEY`, `GROQ_API_KEY`, `FIRECRAWL_API_KEY`, `INDIAN_KANOON_API_KEY`) now utilize `SecretStr` from `pydantic`. This prevents accidental logging or exposure in exception traces. Consumers access the value via `.get_secret_value()`.

## Verification
- Added `tests/unit/test_config.py` to ensure correct loading of development defaults, production validations, and secret handling.
- Verified backend compile readiness via `python -m py_compile app.py`.

## Future State Readiness
This configuration redesign acts as the prerequisite for **Phase 7B**, which will migrate the `sqlite` database to `PostgreSQL`, introduce caching via `Redis`, and containerize the application via `Docker`. The architecture now strictly separates configuration from logic, adhering to 12-factor application design principles.

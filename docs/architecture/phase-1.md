# Phase 1: Test Foundation

## Objective
Establish a reliable, reproducible test foundation for JustiAssist without altering any production behavior.

## Results
- **Baseline Suite (Before Phase 1)**: 3 failed, 1 passed (in ~22s). The failures were due to missing `pytest-asyncio` configuration causing native `async def` methods to crash.
- **New Unit & API Suite (`pytest -q`)**: 27 passed (in ~17.43s).
- **New Integration Suite (`pytest -m integration`)**: 1 passed, 26 deselected (in ~14.68s).

## Architecture Changes
1. **Directory Restructure**
   - Moved expensive manual integration scripts to `tests/scripts/`. These scripts load production FAISS indices and execute raw tests against the full pipeline. They are purposefully omitted from standard `pytest` discovery.
   - Moved heavy full-pipeline index tests (like `test_section_boost.py`) to `tests/integration/` and guarded them with `@pytest.mark.integration`.
   - Created `tests/unit/` for isolated component testing.
   - Created `tests/api/` for FastAPI routing and endpoint smoke testing.

2. **Pytest Configuration**
   - Created `pytest.ini` at the root directory to properly register `asyncio_mode = auto`. This fixes the `async def` crash immediately.
   - Excluded the `tests/scripts/` directory natively via `norecursedirs`.

3. **Dependency Mocking**
   - Created `tests/conftest.py` with tightly scoped mock fixtures (e.g. `mock_llm`, `mock_vector_store`, `mock_kanoon`).
   - Mocked out `JustiAssistCrew.__init__` and `LegalReranker.__init__` via the `mock_lifespan_dependencies` fixture so that FastAPI's lifespan `deps.init()` can boot instantly during `TestClient` API testing.
   - We specifically avoided global `autouse` fixtures to ensure that unit tests, smoke tests, and integration tests can cleanly opt-in to mocked components.

4. **Component Test Coverage**
   - **QueryClassifier**: Verified semantic matching fallback mechanisms and explicit intent routing.
   - **QueryReformulator**: Verified legal acronym expansion, section extraction, and bail query enhancements.
   - **LegalReranker**: Verified algorithmic heuristics (statute presence, entity density).
   - **ConfidenceScorer**: Verified mathematical multi-factor scoring (completeness, redundancy, intent).
   - **ContextBuilder**: Verified grouping logic (Statutory, Case Law, Uploaded).
   - **CitationValidator**: Verified grounding boundaries (missing citations, malformed section formats, empty assertions).
   - **API Routes**: Created an explicit route boundary test to verify that the Phase 0B core routes remain registered.

## Next Steps
The foundation is now clean and deterministic. The next phase can focus on either migrating `tests/scripts/` to standard parametrized integration tests or moving on to Phase 2 (Modularization of retrieval logic).
